"""End-to-end backtest engine tests on synthetic data."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.backtest.engine import BacktestConfig, run_backtest


def _make_bars(close: np.ndarray) -> pd.DataFrame:
    idx = pd.date_range("2022-01-03", periods=len(close), freq="B", tz="UTC")
    c = pd.Series(close, index=idx)
    return pd.DataFrame(
        {
            "open": c.shift(1).fillna(c.iloc[0]),
            "high": c * 1.005,
            "low": c * 0.995,
            "close": c,
            "volume": pd.Series(1_000_000.0, index=idx),
        }
    )


def test_backtest_runs_and_reports_metrics():
    rng = np.random.default_rng(42)
    n = 300
    # Trending-up series with noise.
    close = 100 * np.cumprod(1 + rng.normal(0.0008, 0.012, n))
    bars = _make_bars(close)
    res = run_backtest({"TEST": bars}, BacktestConfig(warmup=50))

    assert "metrics" in res
    m = res["metrics"]
    for key in ("total_return", "cagr", "sharpe", "max_drawdown", "num_trades"):
        assert key in m
    assert len(res["equity_curve"]) > 0
    assert len(res["benchmark_curve"]) > 0
    # Drawdown is non-positive by construction.
    assert m["max_drawdown"] <= 0


def test_stop_loss_caps_losses():
    # Smooth uptrend builds a long position, then a sudden gap-down should
    # trigger the intrabar stop rather than riding the position down.
    up = np.linspace(100, 140, 100)
    after = np.full(60, 108.0)  # deep gap down (below any 5% stop), then flat
    bars = _make_bars(np.concatenate([up, after]))
    res = run_backtest(
        {"TEST": bars},
        BacktestConfig(warmup=50, stop_loss_pct=0.05, take_profit_pct=0.20),
    )
    stops = [t for t in res["trades"] if t["exit_reason"] == "stop_loss"]
    assert len(stops) >= 1
    # Stop-loss bounds the loss near the configured 5% (plus slippage).
    for t in stops:
        assert -0.08 < t["return_pct"] < 0


def test_flat_market_finds_no_edge():
    bars = _make_bars(np.full(200, 100.0) + np.random.default_rng(0).normal(0, 0.05, 200))
    res = run_backtest({"TEST": bars}, BacktestConfig(warmup=50))
    # A dead-flat market: at most a handful of tiny scratch trades and no
    # meaningful P&L either way (the strategy must not invent an edge).
    assert res["metrics"]["num_trades"] <= 8
    assert abs(res["metrics"]["total_return"]) < 0.03
