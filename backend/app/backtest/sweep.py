"""Parameter sweep: how sensitive is the strategy to its key knobs?

Runs the backtest across a 2-D grid (buy-threshold × technical-vs-volatility
weight tilt) and returns a matrix of Sharpe / total-return per cell. A robust
strategy shows a broad plateau of decent results; a fragile (overfit) one shows
a lone spike. The frontend renders this as a heatmap.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

import pandas as pd

from .engine import BacktestConfig, run_backtest

DEFAULT_THRESHOLDS = [0.15, 0.2, 0.25, 0.3, 0.35]
# Tilt = technical share of the technical+volatility budget (rest -> volatility).
DEFAULT_TILTS = [0.3, 0.45, 0.6, 0.75]


def parameter_sweep(
    bars_by_symbol: dict[str, pd.DataFrame],
    config: BacktestConfig,
    thresholds: list[float] | None = None,
    tilts: list[float] | None = None,
) -> dict[str, Any]:
    """Grid backtest over (buy_threshold × tech/vol tilt)."""
    thresholds = thresholds or DEFAULT_THRESHOLDS
    tilts = tilts or DEFAULT_TILTS
    base = dict(config.weights or {})

    cells: list[dict[str, Any]] = []
    for thr in thresholds:
        for tilt in tilts:
            weights = {
                **base,
                "technical": round(tilt, 3),
                "volatility": round(1 - tilt, 3),
            }
            cfg = replace(
                config, buy_threshold=thr, sell_threshold=-thr, weights=weights
            )
            res = run_backtest(bars_by_symbol, cfg)
            m = res.get("metrics", {})
            cells.append(
                {
                    "threshold": thr,
                    "tilt": tilt,
                    "sharpe": m.get("sharpe"),
                    "total_return": m.get("total_return"),
                    "max_drawdown": m.get("max_drawdown"),
                    "num_trades": m.get("num_trades"),
                }
            )
    return {"thresholds": thresholds, "tilts": tilts, "cells": cells}
