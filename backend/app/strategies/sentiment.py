"""News sentiment signal using VADER over recent Alpaca headlines.

VADER is a lightweight, dependency-free lexicon scorer — adequate for headline
polarity and avoids a model download. The signal is the average compound score
of recent headlines, lightly weighted by how many there are (more coverage =>
more confidence, capped).
"""
from __future__ import annotations

from typing import Any

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from .base import SignalResult, clamp

_analyzer = SentimentIntensityAnalyzer()


def score_headlines(news_items: list[dict[str, Any]]) -> SignalResult:
    res = SignalResult()
    if not news_items:
        res.reasons.append("no recent news")
        return res

    compounds: list[float] = []
    for n in news_items:
        text = f"{n.get('headline', '')}. {n.get('summary', '')}".strip()
        if text:
            compounds.append(_analyzer.polarity_scores(text)["compound"])

    if not compounds:
        res.reasons.append("no scorable news text")
        return res

    avg = sum(compounds) / len(compounds)
    # Confidence ramp: 1 headline -> 0.5x, 5+ -> 1.0x.
    confidence = min(1.0, 0.4 + 0.12 * len(compounds))
    res.score = clamp(avg * confidence)

    pos = sum(1 for c in compounds if c > 0.2)
    neg = sum(1 for c in compounds if c < -0.2)
    tone = "positive" if avg > 0.1 else "negative" if avg < -0.1 else "neutral"
    res.reasons.append(
        f"news sentiment {tone} (avg {avg:+.2f} over {len(compounds)} "
        f"headlines: {pos}+ / {neg}-)"
    )
    res.metrics = {
        "avg_compound": avg,
        "count": len(compounds),
        "positive": pos,
        "negative": neg,
    }
    return res.clamp()
