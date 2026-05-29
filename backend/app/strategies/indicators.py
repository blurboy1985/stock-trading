"""Technical indicators (pure pandas/numpy) and the technical signal.

Implemented from first principles rather than via a TA library so the math is
transparent, dependency-light, and stable across Python/pandas versions.
All functions take/return pandas Series aligned to the input index.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import SignalResult, clamp


def sma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(period).mean()


def ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # Wilder's smoothing.
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(100)  # all-gains window -> RSI 100


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def bollinger(
    close: pd.Series, period: int = 20, num_std: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    return mid + num_std * std, mid, mid - num_std * std


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average Directional Index — trend strength (0-100)."""
    up = high.diff()
    down = -low.diff()
    plus_dm = ((up > down) & (up > 0)) * up
    minus_dm = ((down > up) & (down > 0)) * down
    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean().fillna(0)


def technical_signal(df: pd.DataFrame) -> SignalResult:
    """Blend RSI, MACD, MA-crossover and ADX-confirmed trend into [-1, 1]."""
    res = SignalResult()
    if len(df) < 35:  # need enough history for slow EMA / ADX
        res.reasons.append("insufficient history for technical signal")
        return res

    close = df["close"]
    last = float(close.iloc[-1])

    rsi_val = float(rsi(close).iloc[-1])
    macd_line, signal_line, hist = macd(close)
    macd_hist = float(hist.iloc[-1])
    macd_prev = float(hist.iloc[-2])
    sma20 = float(sma(close, 20).iloc[-1])
    sma50 = float(sma(close, 50).iloc[-1]) if len(df) >= 50 else sma20
    adx_val = float(adx(df["high"], df["low"], close).iloc[-1])

    sub = 0.0
    strong_trend = adx_val >= 25
    trend_dir = 1.0 if sma20 > sma50 else -1.0

    # RSI is regime-dependent. In a strong trend it confirms momentum (don't
    # fight the trend); in a range it's a mean-reversion signal.
    if strong_trend:
        sub += (rsi_val - 50) / 100 * 0.4
    else:
        if rsi_val < 30:
            sub += 0.4
            res.reasons.append(f"RSI {rsi_val:.0f} oversold, range-bound (mean-revert up)")
        elif rsi_val > 70:
            sub -= 0.4
            res.reasons.append(f"RSI {rsi_val:.0f} overbought, range-bound (mean-revert down)")
        else:
            sub += (50 - rsi_val) / 100

    # MACD histogram sign + momentum (rising/falling).
    if macd_hist > 0 and macd_hist > macd_prev:
        sub += 0.3
        res.reasons.append("MACD positive & rising")
    elif macd_hist < 0 and macd_hist < macd_prev:
        sub -= 0.3
        res.reasons.append("MACD negative & falling")
    else:
        sub += clamp(macd_hist / max(abs(last) * 0.01, 1e-6)) * 0.1

    # Trend via MA crossover, confirmed by ADX strength.
    if strong_trend:
        sub += 0.4 * trend_dir
        res.reasons.append(
            f"{'up' if trend_dir > 0 else 'down'}trend (SMA20 vs SMA50), "
            f"ADX {adx_val:.0f} strong"
        )
    else:
        sub += 0.15 * trend_dir

    res.score = clamp(sub)
    res.metrics = {
        "rsi": rsi_val,
        "macd_hist": macd_hist,
        "sma20": sma20,
        "sma50": sma50,
        "adx": adx_val,
        "price": last,
    }
    return res.clamp()
