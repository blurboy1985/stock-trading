"""Per-symbol momentum features and a liquidity guardrail.

Momentum / relative strength is a classic standalone alpha factor, but it only
means something *cross-sectionally* — a stock's 12-month return is informative
relative to its peers, not in absolute terms. So this module computes raw,
point-in-time momentum measures per symbol; the universe-level ranking that turns
them into a [-1, 1] signal lives in :mod:`cross_section`.

All measures use closed bars only, so they replay honestly in the backtester.
"""
from __future__ import annotations

import pandas as pd

from .indicators import sma

# Classic 12-1 momentum: 12-month formation, skipping the most recent month to
# sidestep short-term reversal.
SKIP = 21
LONG = 252
MID = 63
REL = 126


def _ret(close: pd.Series, lookback: int, skip: int = 0) -> float | None:
    """Return over ``lookback`` bars ending ``skip`` bars ago, or None."""
    need = lookback + skip + 1
    if len(close) < need:
        return None
    end = -1 - skip
    start = end - lookback
    a = float(close.iloc[start])
    b = float(close.iloc[end])
    return (b / a - 1) if a > 0 else None


def momentum_features(df: pd.DataFrame, benchmark_close: pd.Series | None = None) -> dict:
    """Raw momentum measures for one symbol (None where history is too short)."""
    close = df["close"]
    if len(close) < MID + 2:
        return {"raw": None, "ret_12_1": None, "ret_3m": None, "rel_strength": None,
                "pct_above_200": None}

    ret_12_1 = _ret(close, LONG, SKIP)
    ret_3m = _ret(close, MID)

    long_win = min(200, len(close) - 1)
    ma_long = float(sma(close, long_win).iloc[-1])
    pct_above_200 = (float(close.iloc[-1]) / ma_long - 1) if ma_long > 0 else None

    rel_strength = None
    sym_ret = _ret(close, REL)
    if benchmark_close is not None and sym_ret is not None:
        bench_ret = _ret(benchmark_close, REL)
        if bench_ret is not None:
            rel_strength = sym_ret - bench_ret

    # Composite raw score (all components are returns, so directly comparable).
    parts = [(0.5, ret_12_1), (0.3, ret_3m), (0.2, rel_strength)]
    avail = [(w, v) for w, v in parts if v is not None]
    raw = sum(w * v for w, v in avail) / sum(w for w, _ in avail) if avail else None

    return {
        "raw": raw,
        "ret_12_1": ret_12_1,
        "ret_3m": ret_3m,
        "rel_strength": rel_strength,
        "pct_above_200": pct_above_200,
    }


def liquidity_ok(
    df: pd.DataFrame, min_dollar_volume: float, min_price: float
) -> tuple[bool, str]:
    """Cheap tradability gate: median dollar-volume and a price floor.

    Returns ``(ok, reason)``; ``reason`` is empty when the name passes.
    """
    if len(df) < 20:
        return True, ""  # not enough data to judge — don't block
    close = df["close"]
    vol = df["volume"]
    price = float(close.iloc[-1])
    dollar_vol = float((close.iloc[-20:] * vol.iloc[-20:]).median())

    if price < min_price:
        return False, f"price ${price:.2f} below ${min_price:.0f} floor"
    if dollar_vol < min_dollar_volume:
        return False, f"${dollar_vol/1e6:.1f}M/day below ${min_dollar_volume/1e6:.0f}M min"
    return True, ""
