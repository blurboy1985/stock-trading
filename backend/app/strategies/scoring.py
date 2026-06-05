"""Composite scoring: blend signal families into a ranked BUY/SELL/HOLD call.

Each family produces a :class:`SignalResult` in [-1, 1]; we combine them with
configurable weights (normalized so present signals always sum to 1) into a
final composite score, optionally dampen longs by the market regime, then map
that to an action via thresholds.

Keeping this as the single combination point means the live recommender and the
backtester produce identical decisions from identical inputs.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from .base import SignalResult, clamp
from .earnings import earnings_blackout
from .fundamentals import fundamentals_signal
from .indicators import technical_signal
from .regime import regime_multiplier
from .sentiment import score_headlines
from .volatility import volatility_signal

# Default blend. Technicals + breakout dominate (faster), momentum is the
# cross-sectional tilt, sentiment & fundamentals are slower context. Editable
# via Settings. Renormalized over whichever families are actually present.
DEFAULT_WEIGHTS: dict[str, float] = {
    "technical": 0.30,
    "volatility": 0.25,
    "momentum": 0.15,
    "sentiment": 0.15,
    "fundamentals": 0.15,
}

BUY_THRESHOLD = 0.25
SELL_THRESHOLD = -0.25


def combine(
    results: dict[str, SignalResult],
    weights: dict[str, float] | None = None,
    regime_score: float | None = None,
    regime_hard_gate: float | None = None,
    min_agreement: float = 0.0,
) -> dict[str, Any]:
    """Blend per-family results into a final decision dict.

    ``regime_score`` (in [-1, 1]), when supplied, scales the *positive* part of
    the composite via :func:`regime_multiplier` so longs are throttled in a
    risk-off tape; sells are never dampened.

    ``regime_hard_gate`` (in [-1, 1]), when supplied, is a hard capital-
    preservation switch: in a tape at/below it, new BUYs are blocked outright
    (downgraded to HOLD) rather than merely dampened. Sells are never blocked.
    Price-derived, so the backtester replays it honestly.

    ``min_agreement`` (in [0, 1]) is an entry-selectivity gate: a BUY only fires
    when the weight-share of families voting *long* meets this floor, so a buy
    backed by a lone signal is held back and only multi-signal confluence trades.
    Sells are never gated (exits stay easy). Also price-derived / backtestable.
    """
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}

    # Only weight families that actually produced a result; renormalize.
    active = {k: weights.get(k, 0.0) for k in results}
    total_w = sum(active.values()) or 1.0

    composite = 0.0
    breakdown: dict[str, Any] = {}
    reasons: list[str] = []
    norm_weights: dict[str, float] = {}
    for name, result in results.items():
        w = active.get(name, 0.0) / total_w
        norm_weights[name] = w
        composite += result.score * w
        breakdown[name] = {**result.to_dict(), "weight": round(w, 3)}
        reasons.extend(result.reasons)

    composite = clamp(composite)

    # Regime gate: only dampens longs, never sells.
    mult = 1.0
    if regime_score is not None and composite > 0:
        mult = regime_multiplier(regime_score)
        composite = clamp(composite * mult)

    # Agreement: weight-share of families voting the same direction as the
    # composite. Conviction blends magnitude with that agreement so a strong
    # score backed by a lone signal isn't treated like a unanimous one.
    sign = 1.0 if composite > 0 else (-1.0 if composite < 0 else 0.0)
    agreement = 0.0
    if sign != 0.0:
        for name, result in results.items():
            if result.score * sign > 0:
                agreement += norm_weights.get(name, 0.0)
    conviction = abs(composite) * agreement

    if composite >= BUY_THRESHOLD:
        action = "BUY"
    elif composite <= SELL_THRESHOLD:
        action = "SELL"
    else:
        action = "HOLD"

    # Entry-selectivity gate: require multi-signal confluence to go long.
    agreement_gated = False
    if action == "BUY" and min_agreement > 0 and agreement < min_agreement:
        action = "HOLD"
        agreement_gated = True
        reasons.insert(
            0,
            f"agreement gate: only {agreement:.0%} of weight votes long "
            f"(need {min_agreement:.0%}) — low-confluence buy held back",
        )

    # Hard regime gate: block *new* longs in a clearly risk-off tape.
    regime_gated = False
    if (
        action == "BUY"
        and regime_score is not None
        and regime_hard_gate is not None
        and regime_score <= regime_hard_gate
    ):
        action = "HOLD"
        regime_gated = True
        reasons.insert(
            0,
            f"regime gate: risk-off ({regime_score:+.2f} ≤ {regime_hard_gate:+.2f}) "
            "— new longs blocked",
        )

    return {
        "action": action,
        "score": round(composite, 4),
        "confidence": round(abs(composite), 4),
        "conviction": round(conviction, 4),
        "agreement": round(agreement, 4),
        "regime_score": round(regime_score, 4) if regime_score is not None else None,
        "regime_multiplier": round(mult, 4),
        "regime_gated": regime_gated,
        "agreement_gated": agreement_gated,
        "breakdown": breakdown,
        "reasons": reasons,
    }


def evaluate_symbol(
    symbol: str,
    bars: pd.DataFrame,
    news: list[dict[str, Any]] | None = None,
    weights: dict[str, float] | None = None,
    include_fundamentals: bool = True,
    include_sentiment: bool = True,
    momentum: SignalResult | None = None,
    regime_score: float | None = None,
    liquidity_warning: str | None = None,
    regime_hard_gate: float | None = None,
    min_agreement: float = 0.0,
    sentiment_backend: str = "lexicon",
    sentiment_halflife_days: float = 3.0,
    sentiment_lm_weight: float = 0.5,
    sentiment_llm_model: str | None = None,
    sentiment_llm_query_missing: bool = True,
    sector_baseline: dict[str, float] | None = None,
    info: dict[str, Any] | None = None,
    earnings_blackout_days: int = 0,
    context_mode: str = "blend",
    context_veto_threshold: float = 0.4,
) -> dict[str, Any]:
    """Run every enabled signal on a symbol and return the combined decision.

    ``bars`` is an OHLCV DataFrame; ``news`` is optional pre-fetched headlines.
    ``momentum`` is a pre-computed cross-sectional signal (ranked across the
    universe by the caller). ``liquidity_warning`` — when set, the name is too
    thin to buy and any BUY is downgraded to HOLD. ``sector_baseline`` /
    ``info`` feed sector-relative fundamentals; the ``sentiment_*`` knobs tune
    the news signal (and select the optional LLM backend).
    Sentiment/fundamentals can be disabled (e.g. in fast backtests).

    ``context_mode`` controls how sentiment & fundamentals are used. ``"blend"``
    folds them into the weighted composite (legacy). ``"filter"`` keeps them out
    of the score — so the return-driving decision is the price stack the
    backtester actually validates — and instead uses them only as a *veto*: a
    BUY is downgraded to HOLD when either reads below ``-context_veto_threshold``.
    They stay in the breakdown (weight 0 in filter mode) so the UI still shows them.
    """
    results: dict[str, SignalResult] = {
        "technical": technical_signal(bars),
        "volatility": volatility_signal(bars),
    }
    if momentum is not None:
        results["momentum"] = momentum
    if include_sentiment:
        results["sentiment"] = score_headlines(
            news or [],
            halflife_days=sentiment_halflife_days,
            lm_weight=sentiment_lm_weight,
            backend=sentiment_backend,
            llm_model=sentiment_llm_model,
            llm_query_missing=sentiment_llm_query_missing,
        )
    if include_fundamentals:
        results["fundamentals"] = fundamentals_signal(
            symbol, sector_baseline=sector_baseline, info=info
        )

    # In filter mode the context signals carry zero weight (they don't move the
    # composite) but remain in the breakdown for display; their veto is applied
    # below. Backtests pass neither signal, so this is a no-op there.
    if context_mode == "filter":
        weights = {**(weights or {}), "sentiment": 0.0, "fundamentals": 0.0}

    decision = combine(
        results, weights, regime_score=regime_score,
        regime_hard_gate=regime_hard_gate, min_agreement=min_agreement,
    )
    decision["symbol"] = symbol
    if len(bars):
        decision["price"] = round(float(bars["close"].iloc[-1]), 4)

    # ATR% (per-name volatility) for risk-aware sizing / ranking downstream.
    atr_pct = results["volatility"].metrics.get("atr_pct")
    decision["atr_pct"] = round(float(atr_pct), 6) if atr_pct else None

    # Liquidity guardrail: never *enter* a name too thin to trade safely.
    if liquidity_warning:
        decision["liquidity_warning"] = liquidity_warning
        if decision["action"] == "BUY":
            decision["action"] = "HOLD"
            decision["reasons"] = [
                f"liquidity: {liquidity_warning} (buy suppressed)",
                *decision["reasons"],
            ]

    # Earnings blackout: don't *enter* into an imminent report (gap risk). Held
    # names get a flag (surfaced to the user / exit logic) but aren't force-sold
    # here — that stays a user/risk decision.
    in_blackout, why = earnings_blackout(info, earnings_blackout_days)
    if in_blackout:
        decision["earnings_warning"] = why
        if decision["action"] == "BUY":
            decision["action"] = "HOLD"
            decision["reasons"] = [f"{why} (buy suppressed)", *decision["reasons"]]

    # Context veto (filter mode): a clearly negative sentiment/fundamentals read
    # blocks a new long, but never manufactures a buy on its own.
    if context_mode == "filter":
        vetoes = [
            name
            for name in ("sentiment", "fundamentals")
            if name in results and results[name].score <= -context_veto_threshold
        ]
        if vetoes and decision["action"] == "BUY":
            decision["action"] = "HOLD"
            decision["context_veto"] = vetoes
            decision["reasons"] = [
                f"context veto: weak {', '.join(vetoes)} (buy suppressed)",
                *decision["reasons"],
            ]
    return decision
