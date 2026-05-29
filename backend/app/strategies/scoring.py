"""Composite scoring: blend signal families into a ranked BUY/SELL/HOLD call.

Each family produces a :class:`SignalResult` in [-1, 1]; we combine them with
configurable weights (normalized so present signals always sum to 1) into a
final composite score, then map that to an action via thresholds.

Keeping this as the single combination point means the live recommender and the
backtester produce identical decisions from identical inputs.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from .base import SignalResult, clamp
from .fundamentals import fundamentals_signal
from .indicators import technical_signal
from .sentiment import score_headlines
from .volatility import volatility_signal

# Default blend. Technicals + breakout dominate (faster), sentiment &
# fundamentals are slower-moving context. Editable via Settings.
DEFAULT_WEIGHTS: dict[str, float] = {
    "technical": 0.40,
    "volatility": 0.30,
    "sentiment": 0.15,
    "fundamentals": 0.15,
}

BUY_THRESHOLD = 0.25
SELL_THRESHOLD = -0.25


def combine(
    results: dict[str, SignalResult],
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Blend per-family results into a final decision dict."""
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}

    # Only weight families that actually produced a result; renormalize.
    active = {k: weights.get(k, 0.0) for k in results}
    total_w = sum(active.values()) or 1.0

    composite = 0.0
    breakdown: dict[str, Any] = {}
    reasons: list[str] = []
    for name, result in results.items():
        w = active.get(name, 0.0) / total_w
        composite += result.score * w
        breakdown[name] = {**result.to_dict(), "weight": round(w, 3)}
        reasons.extend(result.reasons)

    composite = clamp(composite)
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
) -> dict[str, Any]:
    """Run every enabled signal on a symbol and return the combined decision.

    ``bars`` is an OHLCV DataFrame; ``news`` is optional pre-fetched headlines.
    Sentiment/fundamentals can be disabled (e.g. in fast backtests).
    """
    results: dict[str, SignalResult] = {
        "technical": technical_signal(bars),
        "volatility": volatility_signal(bars),
    }
    if include_sentiment:
        results["sentiment"] = score_headlines(news or [])
    if include_fundamentals:
        results["fundamentals"] = fundamentals_signal(symbol)

    decision = combine(results, weights)
    decision["symbol"] = symbol
    if len(bars):
        decision["price"] = round(float(bars["close"].iloc[-1]), 4)
    return decision
