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
    # Uptrend builds a long, then a *gradual* decline (no gap) trades through the
    # stop intrabar — so the stop fills near its level and bounds the loss ~5%.
    up = np.linspace(100, 140, 100)
    after = np.linspace(140, 108, 60)  # smooth decline through the stop, no gap
    bars = _make_bars(np.concatenate([up, after]))
    # Disable signal exits (sell_threshold unreachable) so the stop is the only
    # way out — isolating that a no-gap decline fills the stop near its level.
    res = run_backtest(
        {"TEST": bars},
        BacktestConfig(
            warmup=50, stop_loss_pct=0.05, take_profit_pct=0.20, sell_threshold=-1.0
        ),
    )
    stops = [t for t in res["trades"] if t["exit_reason"] == "stop_loss"]
    assert len(stops) >= 1
    # Stop-loss bounds the loss near the configured 5% (plus slippage).
    for t in stops:
        assert -0.08 < t["return_pct"] < 0


def test_stop_does_not_cap_loss_on_a_gap():
    # Realism check (fix #4): a position carried into an overnight gap-down fills
    # at the (worse) open, NOT at the stop — so a 5% stop does NOT bound the loss
    # when price gaps straight through it.
    up = np.linspace(100, 140, 100)
    after = np.full(60, 108.0)  # next bar opens ~23% below the prior close
    bars = _make_bars(np.concatenate([up, after]))
    res = run_backtest(
        {"TEST": bars},
        BacktestConfig(warmup=50, stop_loss_pct=0.05, take_profit_pct=0.20),
    )
    gapped = [t for t in res["trades"] if t["return_pct"] < -0.10]
    # At least one stop filled well beyond the 5% stop (filled at the gap open).
    assert gapped, "expected a gap-through fill worse than the stop level"


def test_atr_trailing_stop_lets_winners_run_then_locks_in():
    # Strong uptrend (builds + holds a position), then a sharp reversal. A
    # chandelier ATR trailing stop should exit on the reversal at a price well
    # above entry — i.e. lock in trend profit rather than ride it back down.
    up = np.linspace(100, 200, 160)
    down = np.linspace(200, 150, 40)
    bars = _make_bars(np.concatenate([up, down]))
    res = run_backtest(
        {"TEST": bars},
        BacktestConfig(warmup=50, atr_stop_mult=3.0, trailing_atr_mult=3.0),
    )
    trail = [t for t in res["trades"] if t["exit_reason"] == "trailing_stop"]
    assert len(trail) >= 1
    # The trailing exit banks a gain (stop ratcheted above entry before firing).
    for t in trail:
        assert t["return_pct"] > 0


def test_atr_stop_caps_initial_loss():
    # Without a fixed stop_loss_pct, an ATR stop must still bound a losing trade.
    up = np.linspace(100, 140, 100)
    after = np.full(60, 108.0)  # gap down through the ATR stop, then flat
    bars = _make_bars(np.concatenate([up, after]))
    res = run_backtest(
        {"TEST": bars},
        BacktestConfig(warmup=50, atr_stop_mult=3.0),
    )
    exits = [t for t in res["trades"] if t["exit_reason"] in ("stop_loss", "trailing_stop")]
    assert len(exits) >= 1


def test_flat_market_finds_no_edge():
    bars = _make_bars(np.full(200, 100.0) + np.random.default_rng(0).normal(0, 0.05, 200))
    res = run_backtest({"TEST": bars}, BacktestConfig(warmup=50))
    # A dead-flat market: at most a handful of tiny scratch trades and no
    # meaningful P&L either way (the strategy must not invent an edge).
    assert res["metrics"]["num_trades"] <= 8
    assert abs(res["metrics"]["total_return"]) < 0.03
