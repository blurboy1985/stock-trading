"""Tests for the quant upgrades: regime, momentum, conviction, sizing, validation."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.backtest.engine import BacktestConfig, run_backtest
from app.backtest.walkforward import walk_forward
from app.services import risk
from app.strategies import scoring
from app.strategies.base import SignalResult
from app.strategies.cross_section import momentum_signal
from app.strategies.momentum import liquidity_ok, momentum_features
from app.strategies.regime import market_regime, regime_multiplier


def _ohlcv(close: np.ndarray) -> pd.DataFrame:
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


# ── Regime ─────────────────────────────────────────────────────────────
def test_regime_directionality():
    up = _ohlcv(np.linspace(100, 200, 260))
    down = _ohlcv(np.linspace(200, 100, 260))
    assert market_regime(up)["label"] == "risk_on"
    assert market_regime(up)["score"] > 0.2
    assert market_regime(down)["label"] == "risk_off"
    assert market_regime(down)["score"] < -0.2


def test_regime_multiplier_only_dampens_downside():
    assert regime_multiplier(0.5) == 1.0      # risk-on: longs untouched
    assert regime_multiplier(0.0) == 1.0
    assert regime_multiplier(-1.0) < 0.5      # deep risk-off: throttled
    assert 0.4 <= regime_multiplier(-1.0) <= 1.0


def test_regime_dampens_positive_composite_in_combine():
    res = {"technical": SignalResult(score=0.8), "volatility": SignalResult(score=0.6)}
    base = scoring.combine(res)
    risk_off = scoring.combine(res, regime_score=-1.0)
    assert risk_off["score"] < base["score"]
    # Sells must never be dampened.
    bear = {"technical": SignalResult(score=-0.8), "volatility": SignalResult(score=-0.6)}
    assert scoring.combine(bear, regime_score=-1.0)["score"] == scoring.combine(bear)["score"]


# ── Cross-sectional momentum ───────────────────────────────────────────
def test_momentum_ranks_cross_section():
    sigs = momentum_signal({"A": 0.5, "B": 0.0, "C": -0.5})
    assert sigs["A"].score > sigs["B"].score > sigs["C"].score
    assert sigs["A"].metrics["rank"] == 1
    assert sigs["C"].metrics["rank"] == 3


def test_momentum_features_positive_in_uptrend():
    up = _ohlcv(np.linspace(100, 180, 120))
    feats = momentum_features(up)
    assert feats["raw"] is not None and feats["raw"] > 0


def test_momentum_signal_neutral_with_one_symbol():
    sigs = momentum_signal({"A": 0.3})
    assert sigs["A"].score == 0.0


# ── Conviction / agreement ─────────────────────────────────────────────
def test_conviction_rewards_agreement():
    agree = scoring.combine(
        {"technical": SignalResult(score=0.7), "volatility": SignalResult(score=0.7)}
    )
    disagree = scoring.combine(
        {"technical": SignalResult(score=0.7), "volatility": SignalResult(score=-0.5)}
    )
    assert agree["agreement"] == 1.0
    assert disagree["agreement"] < 1.0
    assert agree["conviction"] > disagree["conviction"]


# ── Volatility-targeted sizing ─────────────────────────────────────────
def test_vol_target_sizing_inverse_to_volatility():
    kw = dict(target_risk_pct=0.0025, max_position_pct=0.10)
    low = risk.size_position_vol_target(100_000, 100, 0.01, 1.0, **kw)
    high = risk.size_position_vol_target(100_000, 100, 0.05, 1.0, **kw)
    assert low > high  # lower vol -> larger position


def test_vol_target_sizing_scales_with_conviction():
    kw = dict(target_risk_pct=0.0025, max_position_pct=0.10)
    strong = risk.size_position_vol_target(100_000, 100, 0.03, 1.0, **kw)
    weak = risk.size_position_vol_target(100_000, 100, 0.03, 0.2, **kw)
    assert strong > weak


# ── Liquidity guardrail ────────────────────────────────────────────────
def test_liquidity_guardrail_forces_hold(uptrend):
    out = scoring.evaluate_symbol(
        "THIN", uptrend, news=[], include_fundamentals=False,
        include_sentiment=False, liquidity_warning="too thin",
    )
    assert out["action"] == "HOLD"
    assert "liquidity_warning" in out


def test_liquidity_ok_blocks_penny_and_thin():
    cheap = _ohlcv(np.full(40, 2.0))
    assert liquidity_ok(cheap, 1_000_000, 5.0)[0] is False
    liquid = _ohlcv(np.full(40, 100.0))
    assert liquidity_ok(liquid, 1_000_000, 5.0)[0] is True


# ── Backtest integration + walk-forward ────────────────────────────────
def _trending_universe(n=320, seed=7):
    rng = np.random.default_rng(seed)
    out = {}
    for i, sym in enumerate(["AAA", "BBB", "CCC"]):
        drift = 0.0006 + i * 0.0002
        close = 100 * np.cumprod(1 + rng.normal(drift, 0.012, n))
        out[sym] = _ohlcv(close)
    return out


def test_backtest_with_vol_sizing_reports_diagnostics():
    res = run_backtest(
        _trending_universe(),
        BacktestConfig(warmup=60, use_vol_sizing=True),
    )
    m = res["metrics"]
    assert "exposure_pct" in m and 0 <= m["exposure_pct"] <= 1
    assert "turnover" in m
    assert "attribution" in m


def test_walk_forward_runs_out_of_sample():
    res = walk_forward(_trending_universe(n=360), BacktestConfig(warmup=60), folds=3)
    assert "error" not in res
    assert len(res["folds"]) == 3
    for f in res["folds"]:
        assert f["chosen_threshold"] in [0.15, 0.2, 0.25, 0.3, 0.35]
    assert "oos_metrics" in res
