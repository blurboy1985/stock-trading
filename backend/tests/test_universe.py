"""Universe composition for the recommendation scan (build_universe).

Monkeypatches the watchlist + screener so the tests don't touch the DB or the
network — they pin the merge/dedupe/cap/fallback behavior only.
"""
from __future__ import annotations

from app.services import recommender


def _cfg(**over):
    base = {
        "benchmark_symbol": "SPY",
        "universe_source": "most_active",
        "universe_size": 5,
    }
    base.update(over)
    return base


def test_broad_scan_unions_watchlist_movers_and_benchmark(monkeypatch):
    monkeypatch.setattr(recommender, "get_universe", lambda: ["AAPL", "MSFT"])
    monkeypatch.setattr(
        recommender.ac, "get_most_actives", lambda top=100: ["TSLA", "NVDA", "AAPL"]
    )
    universe, wl = recommender.build_universe(_cfg(universe_size=10))

    # Watchlist + benchmark are mandatory; movers fill the rest; AAPL deduped.
    assert universe[:3] == ["AAPL", "MSFT", "SPY"]
    assert set(universe) == {"AAPL", "MSFT", "SPY", "TSLA", "NVDA"}
    assert universe.count("AAPL") == 1
    assert wl == {"AAPL", "MSFT"}


def test_cap_never_drops_watchlist_or_benchmark(monkeypatch):
    monkeypatch.setattr(recommender, "get_universe", lambda: ["AAPL", "MSFT"])
    monkeypatch.setattr(
        recommender.ac, "get_most_actives", lambda top=100: ["TSLA", "NVDA", "AMD"]
    )
    # size=2 leaves no room for movers, but watchlist + benchmark must remain.
    universe, wl = recommender.build_universe(_cfg(universe_size=2))
    assert set(universe) == {"AAPL", "MSFT", "SPY"}


def test_screener_outage_falls_back_to_watchlist(monkeypatch):
    monkeypatch.setattr(recommender, "get_universe", lambda: ["AAPL", "MSFT"])
    monkeypatch.setattr(recommender.ac, "get_most_actives", lambda top=100: [])
    universe, wl = recommender.build_universe(_cfg())
    assert universe == ["AAPL", "MSFT", "SPY"]
    assert wl == {"AAPL", "MSFT"}


def test_watchlist_source_skips_screener(monkeypatch):
    monkeypatch.setattr(recommender, "get_universe", lambda: ["AAPL", "MSFT"])

    def _boom(top=100):
        raise AssertionError("screener must not be called for watchlist source")

    monkeypatch.setattr(recommender.ac, "get_most_actives", _boom)
    universe, wl = recommender.build_universe(_cfg(universe_source="watchlist"))
    assert universe == ["AAPL", "MSFT", "SPY"]
