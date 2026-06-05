from __future__ import annotations

import sys
from types import SimpleNamespace

from app.brokers import ibkr


class _FakeTicker:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.news = [
            {
                "content": {
                    "title": f"{symbol} beats estimates and raises guidance {i}",
                    "summary": "Strong demand supports the outlook.",
                    "provider": {"displayName": "Yahoo Finance"},
                    "canonicalUrl": {"url": f"https://example.com/{symbol}/{i}"},
                    "pubDate": "2026-06-05T12:00:00Z",
                }
            }
            for i in range(3)
        ]


def test_ibkr_yfinance_news_limit_is_per_symbol(monkeypatch):
    """Broad recommender calls must not starve later symbols of news.

    Regression: the IBKR/Yahoo fallback treated ``limit`` as a global cap, so a
    call like get_news([AAPL, MSFT, NVDA], limit=2) returned only AAPL headlines.
    That made most recommendation rows show neutral "no recent news" sentiment.
    """
    fake_yf = SimpleNamespace(Ticker=_FakeTicker)
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)

    rows = ibkr.get_news(["AAPL", "MSFT", "NVDA"], limit=2)

    assert len(rows) == 6
    assert {tuple(row["symbols"]) for row in rows} == {("AAPL",), ("MSFT",), ("NVDA",)}
    assert sum(1 for row in rows if row["symbols"] == ["AAPL"]) == 2
    assert sum(1 for row in rows if row["symbols"] == ["MSFT"]) == 2
    assert sum(1 for row in rows if row["symbols"] == ["NVDA"]) == 2
