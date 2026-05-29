"""Thin wrappers around the Alpaca SDK for market data, news, and trading.

Design notes
------------
* All SDK objects are created lazily so the app (and the test suite) can import
  and run with no credentials configured.
* Every public method raises ``AlpacaUnavailable`` with a clear message when
  credentials are missing, rather than failing deep in the SDK.
* Historical bars are returned as a pandas ``DataFrame`` indexed by timestamp
  with columns ``open/high/low/close/volume`` — the shape every strategy expects.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache
from typing import Any

import pandas as pd

from .config import settings


class AlpacaUnavailable(RuntimeError):
    """Raised when an Alpaca call is attempted without usable credentials."""


def _require_creds() -> None:
    if not settings.has_credentials:
        raise AlpacaUnavailable(
            "Alpaca API credentials are not configured. Add APCA_API_KEY_ID and "
            "APCA_API_SECRET_KEY to backend/.env (free paper account at "
            "https://alpaca.markets)."
        )


@lru_cache
def _trading_client():
    _require_creds()
    from alpaca.trading.client import TradingClient

    return TradingClient(
        settings.apca_api_key_id,
        settings.apca_api_secret_key,
        paper=settings.is_paper,
    )


@lru_cache
def _data_client():
    _require_creds()
    from alpaca.data.historical import StockHistoricalDataClient

    return StockHistoricalDataClient(
        settings.apca_api_key_id, settings.apca_api_secret_key
    )


@lru_cache
def _news_client():
    _require_creds()
    from alpaca.data.historical.news import NewsClient

    return NewsClient(settings.apca_api_key_id, settings.apca_api_secret_key)


# ── Market data ────────────────────────────────────────────────────────


def get_bars(
    symbol: str,
    start: dt.datetime | dt.date | str,
    end: dt.datetime | dt.date | str | None = None,
    timeframe: str = "1Day",
) -> pd.DataFrame:
    """Historical OHLCV bars as a DataFrame indexed by timestamp."""
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    tf_map = {
        "1Day": TimeFrame.Day,
        "1Hour": TimeFrame.Hour,
        "1Min": TimeFrame.Minute,
        "15Min": TimeFrame(15, TimeFrameUnit.Minute),
    }
    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=tf_map.get(timeframe, TimeFrame.Day),
        start=pd.Timestamp(start).to_pydatetime(),
        end=pd.Timestamp(end).to_pydatetime() if end else None,
    )
    bars = _data_client().get_stock_bars(req)
    df = bars.df
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    # Multi-index (symbol, timestamp) -> drop symbol level.
    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(symbol, level="symbol")
    return df[["open", "high", "low", "close", "volume"]]


def get_latest_quote(symbol: str) -> dict[str, Any]:
    """Latest bid/ask/mid for a symbol."""
    from alpaca.data.requests import StockLatestQuoteRequest

    req = StockLatestQuoteRequest(symbol_or_symbols=symbol)
    q = _data_client().get_stock_latest_quote(req)[symbol]
    bid, ask = float(q.bid_price or 0), float(q.ask_price or 0)
    mid = (bid + ask) / 2 if bid and ask else (bid or ask)
    return {
        "symbol": symbol,
        "bid": bid,
        "ask": ask,
        "mid": round(mid, 4),
        "timestamp": q.timestamp.isoformat() if q.timestamp else None,
    }


def get_news(symbols: list[str], limit: int = 20) -> list[dict[str, Any]]:
    """Recent news headlines for the given symbols."""
    from alpaca.data.requests import NewsRequest

    req = NewsRequest(symbols=",".join(symbols), limit=limit)
    resp = _news_client().get_news(req)
    out: list[dict[str, Any]] = []
    for n in resp.data.get("news", []):
        out.append(
            {
                "headline": n.headline,
                "summary": getattr(n, "summary", "") or "",
                "symbols": n.symbols,
                "source": getattr(n, "source", ""),
                "url": getattr(n, "url", ""),
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
        )
    return out


# ── Account / trading ──────────────────────────────────────────────────


def get_account() -> dict[str, Any]:
    a = _trading_client().get_account()
    return {
        "equity": float(a.equity),
        "cash": float(a.cash),
        "buying_power": float(a.buying_power),
        "portfolio_value": float(a.portfolio_value),
        "last_equity": float(a.last_equity),
        "currency": a.currency,
        "is_paper": settings.is_paper,
        "status": str(a.status),
    }


def get_positions() -> list[dict[str, Any]]:
    out = []
    for p in _trading_client().get_all_positions():
        out.append(
            {
                "symbol": p.symbol,
                "qty": float(p.qty),
                "avg_entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price or 0),
                "market_value": float(p.market_value or 0),
                "unrealized_pl": float(p.unrealized_pl or 0),
                "unrealized_plpc": float(p.unrealized_plpc or 0),
                "side": str(p.side),
            }
        )
    return out


def submit_order(
    symbol: str,
    qty: float,
    side: str,
    order_type: str = "market",
    limit_price: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> dict[str, Any]:
    """Submit an order to Alpaca. Risk checks happen BEFORE this is called.

    Bracket orders (stop_loss/take_profit) attach OCO child orders.
    """
    from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
    from alpaca.trading.requests import (
        LimitOrderRequest,
        MarketOrderRequest,
        StopLossRequest,
        TakeProfitRequest,
    )

    side_enum = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
    bracket = stop_loss is not None or take_profit is not None
    common: dict[str, Any] = {
        "symbol": symbol,
        "qty": qty,
        "side": side_enum,
        "time_in_force": TimeInForce.DAY,
    }
    if bracket:
        common["order_class"] = OrderClass.BRACKET
        if take_profit is not None:
            common["take_profit"] = TakeProfitRequest(limit_price=round(take_profit, 2))
        if stop_loss is not None:
            common["stop_loss"] = StopLossRequest(stop_price=round(stop_loss, 2))

    if order_type == "limit" and limit_price is not None:
        req = LimitOrderRequest(limit_price=round(limit_price, 2), **common)
    else:
        req = MarketOrderRequest(**common)

    o = _trading_client().submit_order(req)
    return {
        "alpaca_order_id": str(o.id),
        "symbol": o.symbol,
        "qty": float(o.qty),
        "side": str(o.side),
        "status": str(o.status),
        "submitted_at": o.submitted_at.isoformat() if o.submitted_at else None,
    }


def cancel_order(order_id: str) -> None:
    _trading_client().cancel_order_by_id(order_id)


def list_orders(status: str = "all", limit: int = 50) -> list[dict[str, Any]]:
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest

    status_map = {
        "all": QueryOrderStatus.ALL,
        "open": QueryOrderStatus.OPEN,
        "closed": QueryOrderStatus.CLOSED,
    }
    req = GetOrdersRequest(status=status_map.get(status, QueryOrderStatus.ALL), limit=limit)
    out = []
    for o in _trading_client().get_orders(req):
        out.append(
            {
                "id": str(o.id),
                "symbol": o.symbol,
                "qty": float(o.qty or 0),
                "filled_qty": float(o.filled_qty or 0),
                "side": str(o.side),
                "type": str(o.order_type),
                "status": str(o.status),
                "submitted_at": o.submitted_at.isoformat() if o.submitted_at else None,
            }
        )
    return out


def get_clock() -> dict[str, Any]:
    """Market open/close status."""
    c = _trading_client().get_clock()
    return {
        "is_open": c.is_open,
        "next_open": c.next_open.isoformat() if c.next_open else None,
        "next_close": c.next_close.isoformat() if c.next_close else None,
    }
