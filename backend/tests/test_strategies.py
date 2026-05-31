"""Behavioural tests for indicators, signals, and composite scoring."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from app.strategies import fundamentals as fund
from app.strategies import indicators as ind
from app.strategies import scoring
from app.strategies import sentiment as sent
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


def test_regime_hard_gate_blocks_new_longs():
    bullish = {
        "technical": SignalResult(score=0.8),
        "volatility": SignalResult(score=0.6),
    }
    # Risk-off tape below the gate: a would-be BUY is blocked, not just dampened.
    gated = scoring.combine(bullish, regime_score=-0.7, regime_hard_gate=-0.5)
    assert gated["action"] == "HOLD"
    assert gated["regime_gated"] is True
    # Above the gate the same signals still buy.
    ok = scoring.combine(bullish, regime_score=-0.3, regime_hard_gate=-0.5)
    assert ok["action"] == "BUY"
    assert ok["regime_gated"] is False
    # A SELL is never blocked by the gate.
    bearish = {"technical": SignalResult(score=-0.8)}
    assert scoring.combine(bearish, regime_score=-0.9, regime_hard_gate=-0.5)["action"] == "SELL"


def test_min_agreement_gate_blocks_low_confluence_buy():
    # One strong family carries the composite over the buy line, but agreement
    # (its lone weight-share) is below the gate, so the BUY is held back.
    lone = {
        "technical": SignalResult(score=0.9),
        "volatility": SignalResult(score=-0.1),
        "momentum": SignalResult(score=-0.1),
    }
    gated = scoring.combine(lone, min_agreement=0.6)
    ungated = scoring.combine(lone, min_agreement=0.0)
    assert ungated["action"] == "BUY"
    assert gated["action"] == "HOLD"
    assert gated["agreement_gated"] is True
    # Full confluence clears the same gate.
    allin = {
        "technical": SignalResult(score=0.6),
        "volatility": SignalResult(score=0.6),
        "momentum": SignalResult(score=0.6),
    }
    assert scoring.combine(allin, min_agreement=0.6)["action"] == "BUY"


def test_context_filter_veto_suppresses_buy(uptrend, monkeypatch):
    # In filter mode a strongly negative sentiment read vetoes a BUY but never
    # contributes to the score (weight 0). Force a bearish sentiment signal.
    monkeypatch.setattr(
        scoring, "score_headlines", lambda *a, **k: SignalResult(score=-0.9, reasons=["bad news"])
    )
    out = scoring.evaluate_symbol(
        "TEST", uptrend, news=[{"headline": "x"}],
        include_fundamentals=False, include_sentiment=True,
        context_mode="filter", context_veto_threshold=0.4,
    )
    assert out["action"] == "HOLD"
    assert out.get("context_veto") == ["sentiment"]
    # Sentiment is shown but carries zero weight in the composite.
    assert out["breakdown"]["sentiment"]["weight"] == 0.0


def test_earnings_blackout_suppresses_buy(uptrend):
    soon = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2)
    info = {"earningsTimestamp": soon.timestamp()}
    out = scoring.evaluate_symbol(
        "TEST", uptrend, news=[], include_fundamentals=False, include_sentiment=False,
        info=info, earnings_blackout_days=5,
    )
    assert out["action"] == "HOLD"
    assert "earnings" in out.get("earnings_warning", "")


def test_evaluate_symbol_without_external_calls(uptrend):
    # Disable sentiment/fundamentals to avoid network in unit tests.
    out = scoring.evaluate_symbol(
        "TEST", uptrend, news=[], include_fundamentals=False, include_sentiment=False
    )
    assert out["symbol"] == "TEST"
    assert out["action"] in {"BUY", "SELL", "HOLD"}
    assert "price" in out
    assert set(out["breakdown"]) == {"technical", "volatility"}


# ── sentiment ──────────────────────────────────────────────────────────────


def _news(headline: str, *, days_ago: float = 0.0, now: dt.datetime, summary: str = ""):
    ts = now - dt.timedelta(days=days_ago)
    return {"headline": headline, "summary": summary, "created_at": ts.isoformat()}


def test_sentiment_empty_is_neutral():
    res = sent.score_headlines([])
    assert res.score == 0.0
    assert any("no recent news" in r for r in res.reasons)


def test_sentiment_finance_negative_is_bearish():
    now = dt.datetime(2026, 5, 30, tzinfo=dt.timezone.utc)
    news = [
        _news("Company misses earnings and cuts guidance", now=now),
        _news("Firm faces SEC probe and shareholder lawsuit", now=now),
    ]
    res = sent.score_headlines(news, now=now)
    assert res.score < -0.1


def test_sentiment_positive_is_bullish():
    now = dt.datetime(2026, 5, 30, tzinfo=dt.timezone.utc)
    news = [
        _news("Company beats earnings and raises guidance", now=now),
        _news("Record profit on strong revenue growth", now=now),
    ]
    res = sent.score_headlines(news, now=now)
    assert res.score > 0.1


def test_sentiment_recency_weighting_favors_fresh_news():
    now = dt.datetime(2026, 5, 30, tzinfo=dt.timezone.utc)
    news = [
        _news("Record profit, beats estimates, raises guidance", days_ago=0, now=now),
        _news("Misses earnings, cuts outlook, faces lawsuit", days_ago=20, now=now),
    ]
    # Fresh bullish news with a 3-day half-life should outweigh 20-day-old bearish.
    res = sent.score_headlines(news, halflife_days=3.0, now=now)
    assert res.score > 0


def test_sentiment_dedup_does_not_inflate_count():
    now = dt.datetime(2026, 5, 30, tzinfo=dt.timezone.utc)
    dupe = "Company beats earnings and raises full year guidance"
    res = sent.score_headlines([_news(dupe, now=now), _news(dupe, now=now)], now=now)
    assert res.metrics["count"] == 1
    assert res.metrics["raw_count"] == 2


def test_lm_polarity_directionality():
    assert sent.lm_polarity("record profit and strong growth") > 0
    assert sent.lm_polarity("bankruptcy fraud lawsuit loss") < 0


# ── fundamentals ─────────────────────────────────────────────────────────────

_CHEAP_QUALITY = {
    "trailingPE": 12, "priceToSalesTrailing12Months": 1.5, "pegRatio": 0.8,
    "enterpriseToEbitda": 8, "revenueGrowth": 0.25, "earningsGrowth": 0.3,
    "profitMargins": 0.20, "grossMargins": 0.6, "returnOnEquity": 0.30,
    "freeCashflow": 1e9, "debtToEquity": 30, "currentRatio": 2.5,
}

_DISTRESSED = {
    "trailingPE": 90, "priceToSalesTrailing12Months": 15, "pegRatio": 5,
    "enterpriseToEbitda": 40, "revenueGrowth": -0.1, "earningsGrowth": -0.4,
    "profitMargins": -0.1, "grossMargins": 0.1, "returnOnEquity": -0.2,
    "freeCashflow": -5e8, "debtToEquity": 300, "currentRatio": 0.5,
}


def test_fundamentals_cheap_quality_is_bullish():
    assert fund._score_from_info(_CHEAP_QUALITY).score > 0.3


def test_fundamentals_distressed_is_bearish():
    assert fund._score_from_info(_DISTRESSED).score < -0.3


def test_fundamentals_partial_data_renormalizes():
    res = fund._score_from_info({"revenueGrowth": 0.25})
    assert res.score > 0  # growth-only, but still produces a tilt
    assert "growth_score" in res.metrics


def test_fundamentals_unavailable_is_neutral():
    res = fund._score_from_info({})
    assert res.score == 0.0
    assert any("unavailable" in r for r in res.reasons)


def test_fundamentals_sector_relative_flips_on_baseline():
    info = {"trailingPE": 20}  # isolate the value group
    cheap_vs_peers = fund._score_from_info(info, {"trailing_pe": 40})
    rich_vs_peers = fund._score_from_info(info, {"trailing_pe": 10})
    assert cheap_vs_peers.score > 0 > rich_vs_peers.score


def test_build_sector_baselines_medians_and_min_peers():
    infos = {
        "A": {"sector": "Tech", "trailingPE": 10},
        "B": {"sector": "Tech", "trailingPE": 20},
        "C": {"sector": "Tech", "trailingPE": 30},
        "D": {"sector": "Utilities", "trailingPE": 15},
        "E": {"sector": "Utilities", "trailingPE": 18},
    }
    baselines = fund.build_sector_baselines(infos)
    assert baselines["Tech"]["trailing_pe"] == 20  # median of 10/20/30
    assert "Utilities" not in baselines  # only 2 peers (< min_peers)
