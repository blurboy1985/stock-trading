"""News sentiment signal: finance-tuned, recency-weighted, de-duplicated.

The base scorer blends two lexicons over recent headlines+summaries:

* **VADER** — general-purpose polarity (good at tone, punctuation, intensifiers).
* **Loughran–McDonald** — finance-specific word lists that correct VADER's
  systematic misreads of market vocabulary (see :mod:`.data.lm_lexicon`).

On top of the blend we:

* **De-duplicate** syndicated stories so one wire-report reprinted by ten
  outlets doesn't inflate confidence.
* **Recency-weight** items with an exponential half-life so fresh news drives
  the score and stale news fades.
* **Penalize dispersion** — when headlines strongly disagree, confidence drops
  instead of averaging to a misleading ~0.

An optional LLM backend (:mod:`.sentiment_llm`, off by default) can replace the
per-item polarity step; it falls back to the lexicon blend on any failure so a
scoring cycle never breaks on a network/API problem.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from typing import Any

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from .base import SignalResult, clamp
from .data.lm_lexicon import NEGATIVE, NEGATORS, POSITIVE

_analyzer = SentimentIntensityAnalyzer()

_TOKEN_RE = re.compile(r"[a-z][a-z'\-]+")
_DEFAULT_HALFLIFE_DAYS = 3.0
_DEFAULT_LM_WEIGHT = 0.5
_DUP_JACCARD = 0.8  # token-set overlap above which two headlines are "the same"


# ── lexical scoring ──────────────────────────────────────────────────────


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def lm_polarity(text: str) -> float:
    """Loughran–McDonald polarity in [-1, 1] with simple negation handling."""
    toks = _tokens(text)
    pos = neg = 0
    for i, t in enumerate(toks):
        flip = i > 0 and toks[i - 1] in NEGATORS
        if t in POSITIVE:
            neg += 1 if flip else 0
            pos += 0 if flip else 1
        elif t in NEGATIVE:
            pos += 1 if flip else 0
            neg += 0 if flip else 1
    total = pos + neg
    return (pos - neg) / total if total else 0.0


def _blended_polarity(text: str, lm_weight: float) -> float:
    vader = _analyzer.polarity_scores(text)["compound"]
    lm = lm_polarity(text)
    return clamp(lm_weight * lm + (1.0 - lm_weight) * vader)


# ── de-duplication ───────────────────────────────────────────────────────


def _norm_token_set(text: str) -> frozenset[str]:
    return frozenset(_tokens(text))


def _dedup(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop near-identical headlines (syndicated reprints), keeping the first."""
    kept: list[tuple[frozenset[str], dict[str, Any]]] = []
    for it in items:
        ts = _norm_token_set(it.get("headline", ""))
        if not ts:
            continue
        dup = False
        for seen, _ in kept:
            inter = len(ts & seen)
            union = len(ts | seen) or 1
            if inter / union >= _DUP_JACCARD:
                dup = True
                break
        if not dup:
            kept.append((ts, it))
    return [it for _, it in kept]


# ── recency weighting ────────────────────────────────────────────────────


def _age_days(created_at: str | None, now: dt.datetime) -> float:
    if not created_at:
        return 7.0  # unknown timestamp => treat as a week old (low weight)
    try:
        ts = dt.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=dt.timezone.utc)
        return max(0.0, (now - ts).total_seconds() / 86400.0)
    except (ValueError, TypeError):
        return 7.0


def _recency_weight(created_at: str | None, now: dt.datetime, halflife: float) -> float:
    return 0.5 ** (_age_days(created_at, now) / max(halflife, 0.25))


# ── public signal ────────────────────────────────────────────────────────


def score_headlines(
    news_items: list[dict[str, Any]],
    *,
    halflife_days: float = _DEFAULT_HALFLIFE_DAYS,
    lm_weight: float = _DEFAULT_LM_WEIGHT,
    backend: str = "lexicon",
    llm_model: str | None = None,
    now: dt.datetime | None = None,
) -> SignalResult:
    """Recency-weighted, finance-tuned sentiment over recent news.

    ``backend="llm"`` routes per-item polarity through the Claude scorer
    (:mod:`.sentiment_llm`), falling back to the lexicon blend on any error.
    """
    res = SignalResult()
    if not news_items:
        res.reasons.append("no recent news")
        return res

    now = now or dt.datetime.now(dt.timezone.utc)
    items = _dedup(news_items)
    if not items:
        res.reasons.append("no scorable news text")
        return res

    polarity_fn = _select_backend(backend, items, lm_weight, llm_model)

    weighted_sum = weight_total = 0.0
    polarities: list[float] = []
    weights: list[float] = []
    vader_acc = lm_acc = 0.0
    for it in items:
        text = f"{it.get('headline', '')}. {it.get('summary', '')}".strip()
        if not text:
            continue
        p = polarity_fn(text)
        w = _recency_weight(it.get("created_at"), now, halflife_days)
        polarities.append(p)
        weights.append(w)
        weighted_sum += p * w
        weight_total += w
        vader_acc += _analyzer.polarity_scores(text)["compound"]
        lm_acc += lm_polarity(text)

    if not polarities:
        res.reasons.append("no scorable news text")
        return res

    avg = weighted_sum / weight_total if weight_total else 0.0

    # Dispersion: weight-weighted std of per-item polarity. High disagreement
    # => the average is less trustworthy, so we damp confidence.
    var = (
        sum(w * (p - avg) ** 2 for p, w in zip(polarities, weights)) / weight_total
        if weight_total
        else 0.0
    )
    dispersion = math.sqrt(var)

    n = len(polarities)
    coverage = min(1.0, 0.4 + 0.12 * n)          # 1 item -> 0.52x, 5+ -> 1.0x
    agreement = max(0.3, 1.0 - dispersion)        # noisy => down to 0.3x
    confidence = coverage * agreement
    res.score = clamp(avg * confidence)

    pos = sum(1 for p in polarities if p > 0.2)
    neg = sum(1 for p in polarities if p < -0.2)
    tone = "positive" if avg > 0.1 else "negative" if avg < -0.1 else "mixed/neutral"
    src = "Claude" if backend == "llm" else "finance lexicon"
    res.reasons.append(
        f"news sentiment {tone} (recency-wtd {avg:+.2f} via {src} over {n} "
        f"stories: {pos}+ / {neg}-)"
    )
    res.metrics = {
        "avg_polarity": avg,
        "vader_avg": vader_acc / n,
        "lm_avg": lm_acc / n,
        "dispersion": dispersion,
        "confidence": confidence,
        "count": n,
        "raw_count": len(news_items),
        "positive": pos,
        "negative": neg,
        "backend": backend,
    }
    return res.clamp()


def _select_backend(
    backend: str, items: list[dict[str, Any]], lm_weight: float,
    llm_model: str | None = None,
):
    """Return a ``text -> polarity`` callable for the requested backend.

    The LLM backend scores the whole batch once (cached by headline) and falls
    back to the lexicon blend if the call fails or returns nothing.
    """
    if backend == "llm":
        try:
            from .sentiment_llm import batch_polarity

            scores = batch_polarity(items, model=llm_model)
            if scores:
                return lambda text: clamp(
                    scores.get(text, _blended_polarity(text, lm_weight))
                )
        except Exception:  # noqa: BLE001 — never break a cycle on the LLM path
            pass
    return lambda text: _blended_polarity(text, lm_weight)
