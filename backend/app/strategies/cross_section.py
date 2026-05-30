"""Cross-sectional ranking: turn per-symbol raw momentum into a [-1, 1] signal.

Momentum is only meaningful relative to the rest of the universe, so we z-score
each symbol's raw momentum across the cohort being evaluated *at the same point
in time* and squash to [-1, 1]. Used identically by the live recommender and the
backtester (which both evaluate the whole universe each step).
"""
from __future__ import annotations

from statistics import mean, pstdev

from .base import SignalResult, clamp


def momentum_signal(raw_by_symbol: dict[str, float | None]) -> dict[str, SignalResult]:
    """Map raw momentum -> a ranked SignalResult per symbol.

    Symbols with no raw value (insufficient history) get a neutral 0.0. A z-score
    of ±2 maps to the ±1 extremes.
    """
    valid = {s: v for s, v in raw_by_symbol.items() if v is not None}
    out: dict[str, SignalResult] = {}

    if len(valid) < 2:
        for s in raw_by_symbol:
            out[s] = SignalResult(reasons=["momentum: too few peers to rank"])
        return out

    vals = list(valid.values())
    mu = mean(vals)
    sd = pstdev(vals)
    # Rank 1 = strongest momentum (for display: "RS rank x/N").
    order = sorted(valid, key=lambda s: valid[s], reverse=True)
    rank_of = {s: i + 1 for i, s in enumerate(order)}
    n = len(order)

    for s in raw_by_symbol:
        v = raw_by_symbol.get(s)
        if v is None:
            out[s] = SignalResult(reasons=["momentum: insufficient history"])
            continue
        z = (v - mu) / sd if sd > 0 else 0.0
        score = clamp(z / 2.0)
        rank = rank_of[s]
        pctile = round(1 - (rank - 1) / max(n - 1, 1), 3)
        res = SignalResult(score=score)
        res.metrics = {
            "raw": round(v, 4),
            "zscore": round(z, 3),
            "rank": rank,
            "universe": n,
            "percentile": pctile,
        }
        res.reasons.append(
            f"relative strength rank {rank}/{n} ({pctile:.0%} pctile)"
        )
        out[s] = res.clamp()
    return out
