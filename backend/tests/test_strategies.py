"""Behavioural tests for indicators, signals, and composite scoring."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.strategies import indicators as ind
from app.strategies import scoring
from app.strategies.base import SignalResult
from app.strategies.volatility import volatility_signal


def test_rsi_bounds_and_extremes():
    up = pd.Series(np.arange(1, 50, dtype=float))  # monotonic up
    down = pd.Series(np.arange(50, 1, -1, dtype=float))  # monotonic down
    assert ind.rsi(up).iloc[-1] > 95
    assert ind.rsi(down).iloc[-1] < 5
    r = ind.rsi(pd.Series(np.random.default_rng(1).normal(100, 2, 100)))
    assert r.between(0, 100).all()


def test_macd_shapes(uptrend):
    macd_line, signal_line, hist = ind.macd(uptrend["close"])
    assert len(macd_line) == len(uptrend)
    # In a sustained uptrend the MACD histogram should be positive late.
    assert hist.iloc[-1] > 0


def test_technical_signal_directionality(uptrend, downtrend):
    assert scoring.technical_signal(uptrend).score > 0.1
    assert scoring.technical_signal(downtrend).score < -0.1


def test_volatility_breakout_is_bullish(breakout):
    res = volatility_signal(breakout)
    assert res.score > 0.3
    assert any("breakout" in r for r in res.reasons)


def test_insufficient_history_is_neutral():
    tiny = pd.DataFrame(
        {
            "open": [1, 2],
            "high": [1, 2],
            "low": [1, 2],
            "close": [1.0, 2.0],
            "volume": [1, 1],
        }
    )
    assert scoring.technical_signal(tiny).score == 0.0


def test_combine_renormalizes_and_thresholds():
    bullish = {
        "technical": SignalResult(score=0.8, reasons=["t"]),
        "volatility": SignalResult(score=0.6, reasons=["v"]),
    }
    out = scoring.combine(bullish)
    assert out["action"] == "BUY"
    assert 0 < out["score"] <= 1
    # Weights of present families renormalize to 1.
    assert abs(sum(b["weight"] for b in out["breakdown"].values()) - 1.0) < 1e-9

    bearish = scoring.combine(
        {"technical": SignalResult(score=-0.7), "volatility": SignalResult(score=-0.5)}
    )
    assert bearish["action"] == "SELL"

    neutral = scoring.combine({"technical": SignalResult(score=0.0)})
    assert neutral["action"] == "HOLD"


def test_evaluate_symbol_without_external_calls(uptrend):
    # Disable sentiment/fundamentals to avoid network in unit tests.
    out = scoring.evaluate_symbol(
        "TEST", uptrend, news=[], include_fundamentals=False, include_sentiment=False
    )
    assert out["symbol"] == "TEST"
    assert out["action"] in {"BUY", "SELL", "HOLD"}
    assert "price" in out
    assert set(out["breakdown"]) == {"technical", "volatility"}
