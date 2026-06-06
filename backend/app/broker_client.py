"""Broker facade used by the application.

Exports the existing Alpaca helper function shapes while routing to the selected
broker adapter. Defaults to IBKR.
"""
from __future__ import annotations

from typing import Any

from .config import settings
from .brokers.base import BrokerUnavailable


def _adapter():
    if settings.broker.lower() == "ibkr":
        from .brokers import ibkr
        return ibkr
    # Compatibility escape hatch for old deployments; new default is IBKR.
    from . import alpaca_client
    return alpaca_client


def __getattr__(name: str) -> Any:
    if name == "AlpacaUnavailable":
        return BrokerUnavailable
    return getattr(_adapter(), name)


# Explicit wrappers keep static imports simple and preserve old helper names.
def get_account(): return _adapter().get_account()
def get_positions(): return _adapter().get_positions()
def list_orders(status: str = "all", limit: int = 50): return _adapter().list_orders(status=status, limit=limit)
def get_activities(activity_types: str | None = None, page_size: int = 100): return _adapter().get_activities(activity_types=activity_types, page_size=page_size)
def get_clock(): return _adapter().get_clock()
def get_asset(symbol: str): return _adapter().get_asset(symbol)
def get_latest_quote(symbol: str): return _adapter().get_latest_quote(symbol)
def get_latest_trade_price(symbol: str): return _adapter().get_latest_trade_price(symbol)
def get_bars(symbol: str, start, end=None, timeframe: str = "1Day"): return _adapter().get_bars(symbol, start, end, timeframe)
def get_bars_multi(symbols: list[str], start, end=None, timeframe: str = "1Day"): return _adapter().get_bars_multi(symbols, start, end, timeframe)
def submit_order(*args, **kwargs): return _adapter().submit_order(*args, **kwargs)
def cancel_order(order_id: str): return _adapter().cancel_order(order_id)
def replace_order(order_id: str, **kwargs): return _adapter().replace_order(order_id, **kwargs)
def close_position(symbol: str, **kwargs): return _adapter().close_position(symbol, **kwargs)
def get_portfolio_history(period: str = "1M", timeframe: str = "1D"): return _adapter().get_portfolio_history(period=period, timeframe=timeframe)
def get_news(symbols: list[str], limit: int = 20, include_external: bool = False): return _adapter().get_news(symbols, limit=limit, include_external=include_external)
def get_most_actives(top: int = 100, by: str = "volume"): return _adapter().get_most_actives(top=top, by=by)
def sync_watchlist(symbols: list[str], name: str = "StockSim"): return _adapter().sync_watchlist(symbols, name=name)
