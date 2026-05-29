"""Volatility / breakout signals: ATR, Donchian & Bollinger breakouts, volume.

Captures short-term momentum events: a close breaking out of its recent range,
especially on a volume spike, leans bullish; breakdowns lean bearish.
"""
from __future__ import annotations

import pandas as pd

from .base import SignalResult, clamp
from .indicators import bollinger


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def volatility_signal(df: pd.DataFrame, lookback: int = 20) -> SignalResult:
    res = SignalResult()
    if len(df) < lookback + 5:
        res.reasons.append("insufficient history for volatility signal")
        return res

    close = df["close"]
    high = df["high"]
    low = df["low"]
    vol = df["volume"]
    last = float(close.iloc[-1])

    # Donchian channel (exclude the current bar from the range).
    hi = float(high.iloc[-(lookback + 1) : -1].max())
    lo = float(low.iloc[-(lookback + 1) : -1].min())

    # Require the break to clear the range by a fraction of ATR so marginal
    # noise pokes above/below the prior extreme don't register as breakouts.
    atr_val = float(atr(high, low, close).iloc[-1])
    buffer = 0.5 * atr_val

    # Volume spike vs average.
    avg_vol = float(vol.iloc[-(lookback + 1) : -1].mean())
    last_vol = float(vol.iloc[-1])
    vol_ratio = last_vol / avg_vol if avg_vol else 1.0
    vol_boost = clamp((vol_ratio - 1.0), 0, 1.5)  # only amplifies, 0..1.5

    sub = 0.0
    if last > hi + buffer:
        sub += 0.6 * (1 + 0.4 * vol_boost)
        res.reasons.append(
            f"breakout above {lookback}-day high {hi:.2f}"
            + (f" on {vol_ratio:.1f}x volume" if vol_ratio > 1.5 else "")
        )
    elif last < lo - buffer:
        sub -= 0.6 * (1 + 0.4 * vol_boost)
        res.reasons.append(
            f"breakdown below {lookback}-day low {lo:.2f}"
            + (f" on {vol_ratio:.1f}x volume" if vol_ratio > 1.5 else "")
        )

    # Bollinger band position as a secondary tilt.
    upper, mid, lower = bollinger(close)
    bw = float(upper.iloc[-1] - lower.iloc[-1])
    if bw > 0:
        pos = (last - float(mid.iloc[-1])) / (bw / 2)  # ~-1..1 inside bands
        sub += clamp(pos, -1, 1) * 0.2

    res.score = clamp(sub)
    res.metrics = {
        "donchian_high": hi,
        "donchian_low": lo,
        "volume_ratio": vol_ratio,
        "atr": atr_val,
        "atr_pct": (atr_val / last) if last else 0.0,
    }
    return res.clamp()
