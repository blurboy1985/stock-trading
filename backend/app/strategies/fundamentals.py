"""Fundamentals signal via yfinance: multi-factor, sector-relative.

Four factor groups, each scored to ``[-1, 1]`` and then blended (renormalized
over whichever groups have data, the same graceful-partial pattern as
:func:`strategies.momentum.momentum_features`):

* **Value** — P/E, forward P/E, P/S, PEG, EV/EBITDA. Scored *relative to the
  sector median* when a baseline is supplied (a rich software P/E is not a rich
  utility P/E); otherwise against absolute anchors.
* **Growth** — revenue growth, earnings growth.
* **Quality** — profit & gross margins, ROE, positive free cash flow.
* **Health** — debt/equity, current ratio (a Piotroski-style leverage tilt).

This is a slow-moving valuation/quality tilt, not a trade trigger. Raw yfinance
``info`` is cached for an hour (it changes slowly and yfinance is rate-limited);
the score itself is recomputed each call since it depends on the sector
baseline, which the caller derives from the live universe.
"""
from __future__ import annotations

import time
from statistics import median
from typing import Any

from .base import SignalResult, clamp

# Raw-info cache (the slow, rate-limited part). Scoring is pure and uncached.
_INFO_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_TTL = 3600.0  # 1 hour

# Group weights (renormalized over whichever groups have data).
_GROUP_WEIGHTS = {"value": 0.35, "growth": 0.30, "quality": 0.25, "health": 0.10}

# Valuation metrics that support sector-relative scoring (lower = cheaper).
_VALUE_KEYS = ("trailing_pe", "price_to_sales", "peg", "ev_ebitda")


def _norm_debt_to_equity(raw: float | None) -> float | None:
    """yfinance reports D/E as a percent (e.g. 150.0 == 1.5x). Normalize."""
    if raw is None:
        return None
    return raw / 100.0 if raw > 5 else raw


def _extract(info: dict[str, Any]) -> dict[str, float | None]:
    """Pull the metrics we score out of a yfinance ``info`` dict."""
    return {
        "trailing_pe": info.get("trailingPE") or info.get("forwardPE"),
        "forward_pe": info.get("forwardPE"),
        "price_to_sales": info.get("priceToSalesTrailing12Months"),
        "peg": info.get("pegRatio") or info.get("trailingPegRatio"),
        "ev_ebitda": info.get("enterpriseToEbitda"),
        "revenue_growth": info.get("revenueGrowth"),
        "earnings_growth": info.get("earningsGrowth"),
        "profit_margins": info.get("profitMargins"),
        "gross_margins": info.get("grossMargins"),
        "roe": info.get("returnOnEquity"),
        "free_cash_flow": info.get("freeCashflow"),
        "debt_to_equity": _norm_debt_to_equity(info.get("debtToEquity")),
        "current_ratio": info.get("currentRatio"),
    }


def _rel_value(value: float | None, sector_median: float | None) -> float | None:
    """Cheapness vs. the sector median: cheaper-than-peers => positive."""
    if value is None or value <= 0 or not sector_median or sector_median <= 0:
        return None
    return clamp((sector_median - value) / sector_median)


def _value_subscore(
    m: dict[str, float | None], baseline: dict[str, float] | None
) -> tuple[float | None, list[str]]:
    parts: list[float] = []
    reasons: list[str] = []
    if baseline:
        for key in _VALUE_KEYS:
            s = _rel_value(m.get(key), baseline.get(key))
            if s is not None:
                parts.append(s)
        pe = m.get("trailing_pe")
        med = baseline.get("trailing_pe")
        if pe and med and pe > 0:
            cmp = "below" if pe < med else "above"
            reasons.append(f"P/E {pe:.1f} {cmp} sector median {med:.1f}")
    else:
        pe = m.get("trailing_pe")
        if pe and pe > 0:
            parts.append(clamp((22 - pe) / 30))
            if pe < 15:
                reasons.append(f"low P/E {pe:.1f} (value)")
            elif pe > 45:
                reasons.append(f"rich P/E {pe:.1f}")
        ps = m.get("price_to_sales")
        if ps and ps > 0:
            parts.append(clamp((4 - ps) / 6))
        peg = m.get("peg")
        if peg and peg > 0:
            parts.append(clamp((1.2 - peg) / 1.5))
        ev = m.get("ev_ebitda")
        if ev and ev > 0:
            parts.append(clamp((12 - ev) / 15))
    if not parts:
        return None, reasons
    return sum(parts) / len(parts), reasons


def _growth_subscore(m: dict[str, float | None]) -> tuple[float | None, list[str]]:
    parts: list[float] = []
    reasons: list[str] = []
    rg = m.get("revenue_growth")
    if rg is not None:
        parts.append(clamp(rg / 0.20))
        if rg > 0.15:
            reasons.append(f"revenue growth {rg:.0%}")
        elif rg < 0:
            reasons.append(f"revenue shrinking {rg:.0%}")
    eg = m.get("earnings_growth")
    if eg is not None:
        parts.append(clamp(eg / 0.30))
    if not parts:
        return None, reasons
    return sum(parts) / len(parts), reasons


def _quality_subscore(m: dict[str, float | None]) -> tuple[float | None, list[str]]:
    parts: list[float] = []
    reasons: list[str] = []
    pm = m.get("profit_margins")
    if pm is not None:
        parts.append(clamp(pm / 0.20))
        if pm > 0.15:
            reasons.append(f"healthy margins {pm:.0%}")
        elif pm < 0:
            reasons.append("unprofitable (negative margins)")
    gm = m.get("gross_margins")
    if gm is not None:
        parts.append(clamp((gm - 0.30) / 0.40))
    roe = m.get("roe")
    if roe is not None:
        parts.append(clamp(roe / 0.25))
        if roe > 0.20:
            reasons.append(f"strong ROE {roe:.0%}")
    fcf = m.get("free_cash_flow")
    if fcf is not None:
        parts.append(0.3 if fcf > 0 else -0.3)
    if not parts:
        return None, reasons
    return sum(parts) / len(parts), reasons


def _health_subscore(m: dict[str, float | None]) -> tuple[float | None, list[str]]:
    parts: list[float] = []
    reasons: list[str] = []
    de = m.get("debt_to_equity")
    if de is not None:
        parts.append(clamp((1.0 - de) / 1.5))
        if de > 2.0:
            reasons.append(f"high leverage (D/E {de:.1f})")
    cr = m.get("current_ratio")
    if cr is not None:
        parts.append(clamp((cr - 1.0) / 1.5))
    if not parts:
        return None, reasons
    return sum(parts) / len(parts), reasons


def _score_from_info(
    info: dict[str, Any], sector_baseline: dict[str, float] | None = None
) -> SignalResult:
    res = SignalResult()
    m = _extract(info)

    subs: dict[str, float] = {}
    value_s, value_r = _value_subscore(m, sector_baseline)
    growth_s, growth_r = _growth_subscore(m)
    quality_s, quality_r = _quality_subscore(m)
    health_s, health_r = _health_subscore(m)
    for name, s in (
        ("value", value_s), ("growth", growth_s),
        ("quality", quality_s), ("health", health_s),
    ):
        if s is not None:
            subs[name] = s

    if not subs:
        res.reasons.append("fundamentals unavailable")
        return res

    total_w = sum(_GROUP_WEIGHTS[k] for k in subs) or 1.0
    res.score = clamp(sum(s * _GROUP_WEIGHTS[k] / total_w for k, s in subs.items()))
    res.reasons.extend(value_r + growth_r + quality_r + health_r)

    res.metrics = {
        **{k: v for k, v in m.items() if v is not None},
        **{f"{k}_score": round(v, 3) for k, v in subs.items()},
        "sector_relative": sector_baseline is not None,
    }
    return res.clamp()


def get_info(symbol: str) -> dict[str, Any]:
    """Fetch (and hour-cache) the raw yfinance info dict; ``{}`` on failure."""
    now = time.time()
    cached = _INFO_CACHE.get(symbol)
    if cached and now - cached[0] < _TTL:
        return cached[1]
    info: dict[str, Any] = {}
    try:
        import yfinance as yf

        info = yf.Ticker(symbol).info or {}
    except Exception:  # noqa: BLE001 — yfinance is best-effort
        info = {}
    _INFO_CACHE[symbol] = (now, info)
    return info


def cached_sector(symbol: str) -> str | None:
    """The symbol's GICS sector from the info cache, or ``None`` (no fetch).

    Cache-only on purpose: callers on the hot risk path must never trigger a
    network round-trip. During a scoring cycle the recommender warms this cache
    for the whole universe, so held names are typically resolvable.
    """
    cached = _INFO_CACHE.get(symbol)
    return cached[1].get("sector") if cached and cached[1] else None


def build_sector_baselines(
    infos_by_symbol: dict[str, dict[str, Any]], min_peers: int = 3
) -> dict[str, dict[str, float]]:
    """Median valuation metrics per sector across the supplied universe.

    Sectors with fewer than ``min_peers`` names are omitted (a 2-name median is
    noise); symbols in those sectors fall back to absolute valuation scoring.
    """
    by_sector: dict[str, dict[str, list[float]]] = {}
    for info in infos_by_symbol.values():
        sector = info.get("sector")
        if not sector:
            continue
        m = _extract(info)
        bucket = by_sector.setdefault(sector, {k: [] for k in _VALUE_KEYS})
        for key in _VALUE_KEYS:
            v = m.get(key)
            if v is not None and v > 0:
                bucket[key].append(v)

    baselines: dict[str, dict[str, float]] = {}
    for sector, metrics in by_sector.items():
        medians = {k: median(vals) for k, vals in metrics.items() if len(vals) >= min_peers}
        if medians:
            baselines[sector] = medians
    return baselines


def fundamentals_signal(
    symbol: str,
    sector_baseline: dict[str, float] | None = None,
    info: dict[str, Any] | None = None,
) -> SignalResult:
    """Fundamentals tilt for one symbol.

    ``sector_baseline`` (from :func:`build_sector_baselines`) enables
    sector-relative valuation. ``info`` lets the caller pass a pre-fetched
    yfinance dict to avoid a redundant lookup.
    """
    if info is None:
        info = get_info(symbol)
    if not info:
        res = SignalResult()
        res.reasons.append("fundamentals unavailable")
        return res
    return _score_from_info(info, sector_baseline)
