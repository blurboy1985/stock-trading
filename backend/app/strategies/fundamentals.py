"""Fundamentals signal via yfinance.

Alpaca does not expose fundamentals reliably, so yfinance supplies valuation and
growth metrics. This acts as a slow-moving tilt / universe pre-filter rather
than a trade trigger: cheap-ish valuation + positive growth + healthy margins
nudges the score up; nosebleed valuation or shrinking revenue nudges it down.

Results are cached for an hour since fundamentals change slowly and yfinance is
rate-limited.
"""
from __future__ import annotations

import time
from typing import Any

from .base import SignalResult, clamp

_CACHE: dict[str, tuple[float, SignalResult]] = {}
_TTL = 3600.0  # 1 hour


def _score_from_info(info: dict[str, Any]) -> SignalResult:
    res = SignalResult()
    sub = 0.0

    pe = info.get("trailingPE") or info.get("forwardPE")
    rev_growth = info.get("revenueGrowth")
    margins = info.get("profitMargins")
    mcap = info.get("marketCap")

    if pe is not None and pe > 0:
        if pe < 15:
            sub += 0.3
            res.reasons.append(f"low P/E {pe:.1f} (value)")
        elif pe > 60:
            sub -= 0.3
            res.reasons.append(f"rich P/E {pe:.1f}")
        else:
            sub += (30 - pe) / 100  # mild tilt around P/E 30

    if rev_growth is not None:
        if rev_growth > 0.15:
            sub += 0.3
            res.reasons.append(f"revenue growth {rev_growth:.0%}")
        elif rev_growth < 0:
            sub -= 0.3
            res.reasons.append(f"revenue shrinking {rev_growth:.0%}")

    if margins is not None:
        if margins > 0.15:
            sub += 0.2
            res.reasons.append(f"healthy margins {margins:.0%}")
        elif margins < 0:
            sub -= 0.2
            res.reasons.append("unprofitable (negative margins)")

    res.score = clamp(sub)
    res.metrics = {
        "trailing_pe": pe,
        "revenue_growth": rev_growth,
        "profit_margins": margins,
        "market_cap": mcap,
    }
    return res.clamp()


def fundamentals_signal(symbol: str) -> SignalResult:
    now = time.time()
    cached = _CACHE.get(symbol)
    if cached and now - cached[0] < _TTL:
        return cached[1]

    res = SignalResult()
    try:
        import yfinance as yf

        info = yf.Ticker(symbol).info
        if info and (info.get("trailingPE") or info.get("revenueGrowth")):
            res = _score_from_info(info)
        else:
            res.reasons.append("fundamentals unavailable")
    except Exception as e:  # noqa: BLE001 — yfinance is best-effort
        res.reasons.append(f"fundamentals fetch failed: {type(e).__name__}")

    _CACHE[symbol] = (now, res)
    return res
