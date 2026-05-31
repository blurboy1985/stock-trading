"""Event-level de-dup tests — the guard against multi-source sentiment bias."""
from __future__ import annotations

import datetime as dt

from app.strategies import news_sources as ns


def _item(headline: str, source: str, *, mins_ago: float, now: dt.datetime):
    return {
        "headline": headline,
        "summary": "",
        "symbols": ["AAPL"],
        "source": source,
        "url": f"http://x/{source}/{mins_ago}",
        "created_at": (now - dt.timedelta(minutes=mins_ago)).isoformat(),
    }


def test_event_dedup_collapses_same_event_across_sources():
    now = dt.datetime.now(dt.timezone.utc)
    items = [
        _item("Apple unveils new iPhone with AI features", "Benzinga", mins_ago=10, now=now),
        _item("Apple unveils new iPhone with AI features", "Yahoo", mins_ago=30, now=now),
        _item("Apple sued over patent dispute in Texas", "Finnhub", mins_ago=40, now=now),
    ]
    out = ns.event_dedup(items)
    assert len(out) == 2  # two distinct events, not three articles

    iphone = next(o for o in out if "iPhone" in o["headline"])
    assert iphone["cluster_size"] == 2
    assert iphone["sources"] == ["Benzinga", "Yahoo"]  # contributors recorded


def test_event_dedup_keeps_distinct_events():
    now = dt.datetime.now(dt.timezone.utc)
    items = [
        _item("Tesla beats Q1 delivery estimates", "A", mins_ago=5, now=now),
        _item("Tesla recalls 2 million vehicles over autopilot", "B", mins_ago=15, now=now),
    ]
    out = ns.event_dedup(items)
    assert len(out) == 2


def test_event_dedup_respects_time_window():
    now = dt.datetime.now(dt.timezone.utc)
    # Identical headline, but 5 days apart => separate events (recurring story).
    items = [
        _item("Nvidia announces quarterly dividend", "A", mins_ago=0, now=now),
        _item("Nvidia announces quarterly dividend", "B", mins_ago=60 * 24 * 5, now=now),
    ]
    out = ns.event_dedup(items, window_hours=48)
    assert len(out) == 2


def test_event_dedup_newest_first_and_symbol_union():
    now = dt.datetime.now(dt.timezone.utc)
    a = _item("Apple unveils new iPhone with AI features", "A", mins_ago=10, now=now)
    b = _item("Apple unveils new iPhone with AI features", "B", mins_ago=30, now=now)
    b["symbols"] = ["AAPL", "FOXX"]
    out = ns.event_dedup([b, a])
    assert len(out) == 1
    assert out[0]["symbols"] == ["AAPL", "FOXX"]  # union across the cluster


def test_build_symbol_news_alpaca_only_is_passthrough():
    base = {"AAPL": [{"headline": "h", "source": "benzinga"}], "MSFT": []}
    cfg = {"news_sources": ["alpaca"], "news_scope": "watchlist"}
    out = ns.build_symbol_news(["AAPL", "MSFT"], {"AAPL"}, base, cfg)
    assert out == base  # no extra sources => untouched Alpaca feed
