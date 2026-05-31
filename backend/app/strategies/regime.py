"""Market-regime filter: is it a good time to be buying *at all*?

A single-stock BUY means something very different in a healthy uptrending market
than in the teeth of a bear market. This module distills the broad market (a
benchmark, by default SPY) plus optional breadth into a regime score in
``[-1, +1]`` and a ``regime_multiplier`` that *dampens long exposure* when the
tape is risk-off.

It is a pure, price-derived function — so, unlike sentiment/fundamentals, it can
be replayed honestly in the backtester with no look-ahead (callers pass only
closed bars).
"""
from __future__ import annotations

import pandas as pd

from .base import clamp
from .indicators import sma

# Regime score bands -> human label.
RISK_ON = 0.2
RISK_OFF = -0.2

# How hard a risk-off tape throttles new long exposure (multiplier floor).
MIN_MULTIPLIER = 0.4


def regime_multiplier(regime_score: float) -> float:
    """Scale factor applied to the *positive* part of a composite score.

    Risk-on (score >= 0) leaves longs untouched (1.0); risk-off ramps exposure
    down toward ``MIN_MULTIPLIER`` at the most bearish reading. Sells are never
    dampened — getting *out* should stay easy in any regime.
    """
    if regime_score >= 0:
        return 1.0
    return clamp(1.0 + (1.0 - MIN_MULTIPLIER) * regime_score, MIN_MULTIPLIER, 1.0)


def _label(score: float) -> str:
    if score >= RISK_ON:
        return "risk_on"
    if score <= RISK_OFF:
        return "risk_off"
    return "neutral"


def market_regime(
    benchmark_bars: pd.DataFrame, breadth_pct: float | None = None
) -> dict:
    """Summarize the broad-market regime from a benchmark OHLCV frame.

    ``breadth_pct`` (0..1), if supplied, is the fraction of the universe trading
    above its own long-term trend — a confirmation that the average stock, not
    just the cap-weighted index, is participating.
    """
    reasons: list[str] = []
    # Per-component contributions, so callers/UI can show *how* the score (and
    # thus the risk-on / risk-off label) was built, not just the bottom line.
    components: list[dict] = []
    if benchmark_bars is None or len(benchmark_bars) < 60:
        return {
            "label": "neutral",
            "score": 0.0,
            "multiplier": 1.0,
            "reasons": ["insufficient benchmark history — regime filter idle"],
            "components": [],
            "metrics": {},
        }

    close = benchmark_bars["close"]
    last = float(close.iloc[-1])
    long_win = min(200, len(close) - 1)
    fast = sma(close, 50)
    slow = sma(close, long_win)
    sma_fast = float(fast.iloc[-1])
    sma_slow = float(slow.iloc[-1])

    score = 0.0

    def _add(name: str, contribution: float, detail: str) -> None:
        """Record one component's signed tilt and a human-readable detail."""
        components.append(
            {"name": name, "contribution": round(contribution, 4), "detail": detail}
        )
        reasons.append(detail)

    # 1) Price above/below its long-term trend (the single biggest tell).
    above_long = last > sma_slow
    if above_long:
        score += 0.4
        _add("trend", 0.4, f"benchmark above {long_win}d SMA")
    else:
        score -= 0.4
        _add("trend", -0.4, f"benchmark below {long_win}d SMA")

    # 2) Golden / death cross of the 50d vs the long SMA.
    if sma_fast > sma_slow:
        score += 0.2
        _add("ma_cross", 0.2, "50d above long-term SMA (golden)")
    else:
        score -= 0.2
        _add("ma_cross", -0.2, "50d below long-term SMA (death)")

    # 3) Slope of the long SMA over the last ~20 bars.
    slope_ref = float(slow.iloc[-21]) if len(slow.dropna()) > 21 else sma_slow
    slope = (sma_slow - slope_ref) / slope_ref if slope_ref else 0.0
    slope_contrib = clamp(slope * 20.0, -0.2, 0.2)  # ~1%/20d move ≈ full tilt
    score += slope_contrib
    _add(
        "slope",
        slope_contrib,
        f"long-term SMA {'rising' if slope >= 0 else 'falling'} {slope:+.1%} over ~20d",
    )

    # 4) Drawdown from the trailing high — deep drawdowns are risk-off.
    hi_win = min(252, len(close))
    trailing_high = float(close.iloc[-hi_win:].max())
    dd = last / trailing_high - 1 if trailing_high else 0.0
    if dd <= -0.10:
        score -= 0.2
        _add("drawdown", -0.2, f"{dd:.0%} off the {hi_win}d high")

    # 5) Optional breadth confirmation.
    if breadth_pct is not None:
        breadth_contrib = clamp((breadth_pct - 0.5) * 0.8, -0.2, 0.2)
        score += breadth_contrib
        _add("breadth", breadth_contrib, f"breadth {breadth_pct:.0%} above trend")

    score = clamp(score)
    return {
        "label": _label(score),
        "score": round(score, 4),
        "multiplier": round(regime_multiplier(score), 4),
        "reasons": reasons,
        "components": components,
        "metrics": {
            "price": round(last, 2),
            "sma_fast": round(sma_fast, 2),
            "sma_long": round(sma_slow, 2),
            "long_window": long_win,
            "slope": round(slope, 4),
            "drawdown_from_high": round(dd, 4),
            "breadth_pct": round(breadth_pct, 4) if breadth_pct is not None else None,
        },
    }


def breadth_above_trend(
    bars_by_symbol: dict[str, pd.DataFrame], window: int = 200
) -> float | None:
    """Fraction of symbols trading above their own ``window``-day SMA."""
    above = 0
    counted = 0
    for df in bars_by_symbol.values():
        if df is None or len(df) < 30:
            continue
        close = df["close"]
        w = min(window, len(close) - 1)
        ma = float(sma(close, w).iloc[-1])
        if ma == ma:  # not NaN
            counted += 1
            if float(close.iloc[-1]) > ma:
                above += 1
    return (above / counted) if counted else None
