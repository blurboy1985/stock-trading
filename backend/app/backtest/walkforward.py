"""Walk-forward analysis: honest out-of-sample validation.

A single backtest is easy to overfit — you can always find a threshold that
looks great in hindsight. Walk-forward splits history into consecutive
train/test folds: on each *train* slice we pick the best ``buy_threshold`` (from
a small grid), then trade that choice *only on the next, unseen test slice*. The
test fold never informs its own parameters, so the stitched-together test-fold
equity curve is a fair estimate of how the strategy would have performed live.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

import pandas as pd

from .engine import BacktestConfig, run_backtest
from .metrics import compute_metrics

DEFAULT_THRESHOLD_GRID = [0.15, 0.2, 0.25, 0.3, 0.35]


def _slice(bars: dict[str, pd.DataFrame], start: int, end: int) -> dict[str, pd.DataFrame]:
    return {s: df.iloc[start:end] for s, df in bars.items()}


def _score(metrics: dict[str, Any]) -> float:
    """Selection objective on the train fold: Sharpe, tie-broken by return."""
    if "error" in metrics:
        return float("-inf")
    return metrics.get("sharpe", 0.0) + 1e-6 * metrics.get("total_return", 0.0)


def walk_forward(
    bars_by_symbol: dict[str, pd.DataFrame],
    config: BacktestConfig,
    folds: int = 4,
    threshold_grid: list[float] | None = None,
) -> dict[str, Any]:
    """Run ``folds`` train/test splits and stitch the out-of-sample results."""
    grid = threshold_grid or DEFAULT_THRESHOLD_GRID

    # Use the shortest series length to lay out aligned fold boundaries.
    min_len = min(len(df) for df in bars_by_symbol.values())
    usable = min_len - config.warmup
    if folds < 2 or usable < folds * (config.warmup + 10):
        return {"error": "not enough history for the requested number of folds"}

    seg = usable // (folds + 1)  # one warmup-train segment + N test segments
    fold_reports: list[dict[str, Any]] = []
    oos_curve: list[dict[str, Any]] = []
    oos_trades: list[dict[str, Any]] = []
    equity = config.starting_cash

    for k in range(folds):
        train_end = config.warmup + seg * (k + 1)
        test_end = config.warmup + seg * (k + 2)
        train_end = min(train_end, min_len)
        test_end = min(test_end, min_len)
        # Train slice always starts at 0 so warmup history is present.
        train_bars = _slice(bars_by_symbol, 0, train_end)
        # Test slice carries enough lead-in for warmup before its trading window.
        test_start = max(0, train_end - config.warmup)
        test_bars = _slice(bars_by_symbol, test_start, test_end)

        # 1) Pick the best threshold on the train fold.
        best_thr, best_obj = config.buy_threshold, float("-inf")
        for thr in grid:
            tcfg = replace(config, buy_threshold=thr, sell_threshold=-thr)
            res = run_backtest(train_bars, tcfg)
            obj = _score(res.get("metrics", {"error": 1}))
            if obj > best_obj:
                best_obj, best_thr = obj, thr

        # 2) Trade that choice on the unseen test fold, compounding equity.
        tcfg = replace(
            config, buy_threshold=best_thr, sell_threshold=-best_thr,
            starting_cash=equity,
        )
        test_res = run_backtest(test_bars, tcfg)
        tm = test_res.get("metrics", {})
        if "error" not in tm:
            equity = tm.get("final_equity", equity)
            oos_curve.extend(test_res.get("equity_curve", []))
            oos_trades.extend(test_res.get("trades", []))
        fold_reports.append(
            {
                "fold": k + 1,
                "chosen_threshold": best_thr,
                "test_metrics": tm,
            }
        )

    oos_metrics = compute_metrics(oos_curve, oos_trades, config.starting_cash)
    return {
        "folds": fold_reports,
        "oos_metrics": oos_metrics,
        "oos_equity_curve": oos_curve,
        "oos_trades": oos_trades,
    }
