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
) -> dict[str, Any]:
    """Blend per-family results into a final decision dict.

    ``regime_score`` (in [-1, 1]), when supplied, scales the *positive* part of
    the composite via :func:`regime_multiplier` so longs are throttled in a
    risk-off tape; sells are never dampened.
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

    return {
        "action": action,
        "score": round(composite, 4),
        "confidence": round(abs(composite), 4),
        "conviction": round(conviction, 4),
        "agreement": round(agreement, 4),
        "regime_score": round(regime_score, 4) if regime_score is not None else None,
        "regime_multiplier": round(mult, 4),
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
) -> dict[str, Any]:
    """Run every enabled signal on a symbol and return the combined decision.

    ``bars`` is an OHLCV DataFrame; ``news`` is optional pre-fetched headlines.
    ``momentum`` is a pre-computed cross-sectional signal (ranked across the
    universe by the caller). ``liquidity_warning`` — when set, the name is too
    thin to buy and any BUY is downgraded to HOLD.
    Sentiment/fundamentals can be disabled (e.g. in fast backtests).
    """
    results: dict[str, SignalResult] = {
        "technical": technical_signal(bars),
        "volatility": volatility_signal(bars),
    }
    if momentum is not None:
        results["momentum"] = momentum
    if include_sentiment:
        results["sentiment"] = score_headlines(news or [])
    if include_fundamentals:
        results["fundamentals"] = fundamentals_signal(symbol)

    decision = combine(results, weights, regime_score=regime_score)
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
    return decision
