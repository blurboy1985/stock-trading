"""IBKR/TWS broker adapter using ib_insync.

The connection is deliberately lazy: importing the app never imports ib_insync or
opens a socket. All tests mock the IB object; no real orders are submitted.
"""
from __future__ import annotations

import datetime as dt
import time
from functools import lru_cache
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from ..config import settings
from .base import BrokerUnavailable, enumval, safe_float

_ib: Any | None = None


def _ib_class():
    try:
        from ib_insync import IB
    except Exception as exc:  # noqa: BLE001
        raise BrokerUnavailable(
            "IBKR broker requires ib_insync. Install backend requirements and "
            "start TWS/Gateway with API access enabled."
        ) from exc
    return IB


def _connect():
    global _ib
    if _ib is None:
        _ib = _ib_class()()
    if not _ib.isConnected():
        try:
            _ib.connect(settings.ibkr_host, settings.ibkr_port, clientId=settings.ibkr_client_id, timeout=5)
        except Exception as exc:  # noqa: BLE001
            raise BrokerUnavailable(
                "IBKR is not connected. Start TWS/IB Gateway, enable Socket API, "
                f"and verify IBKR_HOST={settings.ibkr_host} IBKR_PORT={settings.ibkr_port} "
                f"IBKR_CLIENT_ID={settings.ibkr_client_id}."
            ) from exc
    return _ib


def _stock(symbol: str):
    try:
        from ib_insync import Stock
    except Exception as exc:  # noqa: BLE001
        return SimpleNamespace(symbol=symbol.upper(), exchange="SMART", currency="USD")
    return Stock(symbol.upper(), "SMART", "USD")


def _market_order(action: str, qty: float):
    try:
        from ib_insync import MarketOrder
    except Exception as exc:  # noqa: BLE001
        return SimpleNamespace(action=action.upper(), totalQuantity=qty, orderType="MKT", account=settings.ibkr_account or "")
    return MarketOrder(action.upper(), qty, account=settings.ibkr_account or "")


def _limit_order(action: str, qty: float, price: float):
    try:
        from ib_insync import LimitOrder
    except Exception as exc:  # noqa: BLE001
        return SimpleNamespace(action=action.upper(), totalQuantity=qty, orderType="LMT", lmtPrice=round(float(price), 2), account=settings.ibkr_account or "")
    return LimitOrder(action.upper(), qty, round(float(price), 2), account=settings.ibkr_account or "")


def _require_order_enabled(confirm_live: bool = False) -> None:
    if not settings.trading_enabled:
        raise BrokerUnavailable("Order submission is disabled. Set TRADING_ENABLED=true to permit broker orders.")
    if not settings.is_paper and not (settings.live_trading and confirm_live):
        raise BrokerUnavailable("Live IBKR orders require IBKR_TRADING_MODE=live, LIVE_TRADING=true, and confirm_live=true.")


def _account_id(ib) -> str:
    if settings.ibkr_account:
        return settings.ibkr_account
    accounts = list(ib.managedAccounts() or [])
    return accounts[0] if accounts else ""


def _summary_map(ib) -> dict[str, Any]:
    account = _account_id(ib)
    rows = ib.accountSummary(account) if account else ib.accountSummary()
    return {getattr(r, "tag", ""): r for r in rows or []}


def get_account() -> dict[str, Any]:
    ib = _connect()
    account = _account_id(ib)
    sm = _summary_map(ib)

    def val(tag: str, default: float = 0.0) -> float:
        return safe_float(getattr(sm.get(tag), "value", None), default)

    equity = val("NetLiquidation")
    cash = val("TotalCashValue")
    buying_power = val("BuyingPower", cash)
    gross = val("GrossPositionValue")
    currency = getattr(sm.get("NetLiquidation"), "currency", "USD") or "USD"
    return {
        "account_number": account,
        "equity": equity,
        "last_equity": equity,
        "cash": cash,
        "buying_power": buying_power,
        "portfolio_value": equity,
        "long_market_value": max(gross, 0.0),
        "short_market_value": abs(min(gross, 0.0)),
        "position_market_value": gross,
        "regt_buying_power": buying_power,
        "daytrading_buying_power": buying_power,
        "initial_margin": val("InitMarginReq"),
        "maintenance_margin": val("MaintMarginReq"),
        "accrued_fees": 0.0,
        "daytrade_count": 0,
        "pattern_day_trader": False,
        "trading_blocked": False,
        "account_blocked": False,
        "currency": currency,
        "is_paper": settings.is_paper,
        "status": "active",
    }


def get_positions() -> list[dict[str, Any]]:
    ib = _connect()
    out: list[dict[str, Any]] = []
    for p in ib.positions() or []:
        c = getattr(p, "contract", None)
        sym = getattr(c, "symbol", "")
        qty = safe_float(getattr(p, "position", 0))
        avg = safe_float(getattr(p, "avgCost", 0))
        price = get_latest_trade_price(sym) or avg
        mv = qty * price
        out.append({
            "symbol": sym,
            "qty": qty,
            "qty_available": qty,
            "avg_entry_price": avg,
            "current_price": price,
            "lastday_price": price,
            "market_value": mv,
            "cost_basis": qty * avg,
            "unrealized_pl": mv - qty * avg,
            "unrealized_plpc": ((price - avg) / avg) if avg else 0.0,
            "unrealized_intraday_pl": 0.0,
            "unrealized_intraday_plpc": 0.0,
            "change_today": 0.0,
            "asset_class": "us_equity",
            "exchange": getattr(c, "exchange", "SMART") or "SMART",
            "side": "long" if qty >= 0 else "short",
        })
    return out


def get_clock() -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc)
    # US regular-session approximation; avoids requiring a broker calendar call.
    ny = now.astimezone(ZoneInfo("America/New_York"))
    is_weekday = ny.weekday() < 5
    is_open = is_weekday and dt.time(9, 30) <= ny.time() <= dt.time(16, 0)
    return {"is_open": is_open, "next_open": None, "next_close": None}


@lru_cache(maxsize=2048)
def get_asset(symbol: str) -> dict[str, Any]:
    sym = symbol.upper()
    return {"symbol": sym, "name": sym, "exchange": "SMART", "tradable": True, "fractionable": False}


def get_latest_quote(symbol: str) -> dict[str, Any]:
    ib = _connect()
    contract = _stock(symbol)
    ticker = ib.reqMktData(contract, "", False, False)
    try:
        ib.sleep(1)
    except Exception:  # noqa: BLE001
        pass
    bid = safe_float(getattr(ticker, "bid", 0))
    ask = safe_float(getattr(ticker, "ask", 0))
    last = safe_float(getattr(ticker, "last", 0))
    mid = (bid + ask) / 2 if bid and ask else (bid or ask or last)
    return {"symbol": symbol.upper(), "bid": bid, "ask": ask, "mid": round(mid, 4), "timestamp": dt.datetime.now(dt.timezone.utc).isoformat()}


def get_latest_trade_price(symbol: str) -> float | None:
    try:
        q = get_latest_quote(symbol)
        return safe_float(q.get("mid")) or None
    except Exception:  # noqa: BLE001
        return None


def _duration(start: dt.datetime | dt.date | str, end: dt.datetime | dt.date | str | None) -> str:
    s = pd.Timestamp(start)
    e = pd.Timestamp(end) if end else pd.Timestamp.utcnow()
    days = max(1, int((e - s).days) + 1)
    return f"{days} D" if days < 365 else f"{max(1, days // 365)} Y"


def get_bars(symbol: str, start: dt.datetime | dt.date | str, end: dt.datetime | dt.date | str | None = None, timeframe: str = "1Day") -> pd.DataFrame:
    ib = _connect()
    bar_size = {"1Day": "1 day", "1Hour": "1 hour", "1Min": "1 min", "15Min": "15 mins"}.get(timeframe, "1 day")
    end_dt = "" if end is None else pd.Timestamp(end).strftime("%Y%m%d %H:%M:%S")
    bars = ib.reqHistoricalData(_stock(symbol), endDateTime=end_dt, durationStr=_duration(start, end), barSizeSetting=bar_size, whatToShow="TRADES", useRTH=True, formatDate=1)
    rows = [{"timestamp": pd.Timestamp(b.date), "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume} for b in bars or []]
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    return pd.DataFrame(rows).set_index("timestamp")[["open", "high", "low", "close", "volume"]]


def get_bars_multi(symbols: list[str], start: dt.datetime | dt.date | str, end: dt.datetime | dt.date | str | None = None, timeframe: str = "1Day") -> dict[str, pd.DataFrame]:
    return {s: df for s in symbols if not (df := get_bars(s, start, end, timeframe)).empty}


def submit_order(symbol: str, qty: float, side: str, order_type: str = "market", limit_price: float | None = None, stop_loss: float | None = None, take_profit: float | None = None, confirm_live: bool = False) -> dict[str, Any]:
    _require_order_enabled(confirm_live)
    ib = _connect()
    action = "BUY" if side.lower() == "buy" else "SELL"
    order = _limit_order(action, qty, limit_price) if order_type == "limit" and limit_price is not None else _market_order(action, qty)
    # Stop-loss/take-profit bracket support is intentionally conservative in the
    # first IBKR adapter: risk math is preserved, but unsupported child legs are
    # not synthesized until covered by integration testing against a paper TWS.
    trade = ib.placeOrder(_stock(symbol), order)
    status = enumval(getattr(getattr(trade, "orderStatus", None), "status", "submitted"), "submitted")
    oid = str(getattr(getattr(trade, "order", None), "orderId", ""))
    return {
        "broker_order_id": oid,
        "alpaca_order_id": oid,
        "symbol": symbol.upper(),
        "qty": float(qty),
        "side": side.lower(),
        "status": status,
        "submitted_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def cancel_order(order_id: str) -> None:
    ib = _connect()
    for trade in ib.trades() or []:
        if str(getattr(getattr(trade, "order", None), "orderId", "")) == str(order_id):
            ib.cancelOrder(trade.order)
            return
    raise BrokerUnavailable(f"IBKR order {order_id} was not found in open trades.")


def replace_order(order_id: str, *, stop_price: float | None = None, limit_price: float | None = None) -> dict[str, Any]:
    raise BrokerUnavailable("IBKR order replace is not available through this adapter yet; cancel and resubmit instead.")


def close_position(symbol: str, confirm_live: bool = False) -> dict[str, Any]:
    _require_order_enabled(confirm_live)
    sym = symbol.upper()
    pos = next((p for p in get_positions() if p["symbol"] == sym), None)
    if not pos:
        raise BrokerUnavailable(f"No IBKR position found for {sym}.")
    side = "sell" if float(pos["qty"]) > 0 else "buy"
    return submit_order(sym, abs(float(pos["qty"])), side, confirm_live=confirm_live)


def list_orders(status: str = "all", limit: int = 50) -> list[dict[str, Any]]:
    ib = _connect()
    out: list[dict[str, Any]] = []
    for trade in (ib.trades() or [])[:limit]:
        order = getattr(trade, "order", None)
        contract = getattr(trade, "contract", None)
        st = getattr(trade, "orderStatus", None)
        state = enumval(getattr(st, "status", ""))
        if status == "open" and state in {"filled", "cancelled", "inactive"}:
            continue
        if status == "closed" and state not in {"filled", "cancelled", "inactive"}:
            continue
        out.append({"id": str(getattr(order, "orderId", "")), "broker_order_id": str(getattr(order, "orderId", "")), "symbol": getattr(contract, "symbol", ""), "qty": safe_float(getattr(order, "totalQuantity", 0)), "filled_qty": safe_float(getattr(st, "filled", 0)), "filled_avg_price": safe_float(getattr(st, "avgFillPrice", 0)) or None, "side": enumval(getattr(order, "action", "")), "type": enumval(getattr(order, "orderType", "")), "order_class": "", "time_in_force": getattr(order, "tif", "DAY"), "limit_price": safe_float(getattr(order, "lmtPrice", 0)) or None, "stop_price": safe_float(getattr(order, "auxPrice", 0)) or None, "status": state, "extended_hours": False, "submitted_at": None, "filled_at": None})
    return out


def get_activities(activity_types: str | None = None, page_size: int = 100) -> list[dict[str, Any]]:
    return []


def get_portfolio_history(period: str = "1M", timeframe: str = "1D") -> dict[str, Any]:
    acct = get_account()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    equity = acct["equity"]
    return {"period": period, "timeframe": timeframe, "base_value": equity, "points": [{"time": now, "equity": equity, "profit_loss": 0.0, "profit_loss_pct": 0.0}], "total_pl": 0.0, "total_pl_pct": 0.0}


def get_news(symbols: list[str], limit: int = 20, include_external: bool = False) -> list[dict[str, Any]]:
    """Best-effort no-key Yahoo Finance news fallback for sentiment."""
    out: list[dict[str, Any]] = []
    try:
        import yfinance as yf
    except Exception:  # noqa: BLE001
        return []
    for symbol in symbols:
        try:
            rows = getattr(yf.Ticker(symbol), "news", None) or []
        except Exception:  # noqa: BLE001
            continue
        for n in rows[:limit]:
            content = n.get("content") if isinstance(n, dict) else None
            data = content if isinstance(content, dict) else n
            headline = (data.get("title") or data.get("headline") or "").strip()
            if not headline:
                continue
            provider = data.get("provider") or {}
            click = data.get("clickThroughUrl") or data.get("canonicalUrl") or {}
            published = data.get("pubDate") or data.get("providerPublishTime")
            created = pd.Timestamp(published).to_pydatetime() if published else None
            out.append({
                "headline": headline,
                "summary": data.get("summary") or "",
                "symbols": [symbol.upper()],
                "source": provider.get("displayName") if isinstance(provider, dict) else "Yahoo Finance",
                "url": click.get("url") if isinstance(click, dict) else data.get("link") or "",
                "created_at": created.isoformat() if created else None,
            })
            if len(out) >= limit:
                return out
    return out


def get_most_actives(top: int = 100, by: str = "volume") -> list[str]:
    return []


def sync_watchlist(symbols: list[str], name: str = "StockSim") -> dict[str, Any]:
    return {"symbols": [s.strip().upper() for s in symbols if s.strip()], "action": "noop"}
