"""IBKR/TWS broker adapter using ib_insync.

The connection is deliberately lazy: importing the app never imports ib_insync or
opens a socket. All tests mock the IB object; no real orders are submitted.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import threading
import time
from functools import lru_cache
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select

from ..config import settings
from ..db import SessionLocal
from ..models import OrderRecord
from .base import BrokerUnavailable, enumval, safe_float

_ib: Any | None = None
_connect_lock = threading.RLock()
_ib_op_lock = threading.RLock()


def _ensure_event_loop() -> None:
    """Guarantee a current event loop in the calling thread.

    eventkit/ib_insync expect ``asyncio.get_event_loop()`` to return a loop, but
    FastAPI runs sync endpoints across a pool of worker threads, none of which
    has a loop, and Python 3.12+ no longer creates one implicitly. Without this,
    a broker call on a fresh worker thread raises "There is no current event loop
    in thread 'AnyIO worker thread'" instead of a clean BrokerUnavailable.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("event loop is closed")
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


def _ib_class():
    _ensure_event_loop()
    try:
        from ib_insync import IB
    except Exception as exc:  # noqa: BLE001
        raise BrokerUnavailable(
            "IBKR broker requires ib_insync. Install backend requirements and "
            "start TWS/Gateway with API access enabled."
        ) from exc
    return IB


def _connect() -> Any:
    global _ib
    _ensure_event_loop()
    with _connect_lock:
        if _ib is None:
            _ib = _ib_class()()
            try:
                _ib.RequestTimeout = 2
            except Exception:
                pass
            try:
                # ib_insync's connect sync also issues reqAccountUpdatesMulti
                # for small account lists. Some IB Gateway builds reject the
                # blank model/group argument with error 321 ("Group name cannot
                # be null"). The adapter only needs single-account cached
                # values/portfolio rows, so disable that automatic multi-account
                # request before connecting.
                _ib.MaxSyncedSubAccounts = 0
            except Exception:
                pass
        assert _ib is not None
        if not _ib.isConnected():
            last_exc: Exception | None = None
            connected = False
            client_ids = [settings.ibkr_client_id, settings.ibkr_client_id + 1, settings.ibkr_client_id + 2]
            for client_id in dict.fromkeys(client_ids):
                try:
                    # Use ib_insync's full connect/sync path so account values,
                    # portfolio rows, positions, and open orders reflect the
                    # broker's current state. A low-level socket-only handshake
                    # leaves ib.trades()/accountValues() as stale in-memory
                    # state and can make old PendingSubmit orders appear active.
                    _ib.connect(
                        settings.ibkr_host,
                        settings.ibkr_port,
                        clientId=client_id,
                        timeout=5,
                    )
                    connected = True
                    break
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    try:
                        _ib.disconnect()
                    except Exception:
                        pass
            if not connected:
                detail = f" {type(last_exc).__name__}: {last_exc}" if last_exc else ""
                raise BrokerUnavailable(
                    "IBKR is not connected. Start TWS/IB Gateway, enable Socket API, "
                    f"and verify IBKR_HOST={settings.ibkr_host} IBKR_PORT={settings.ibkr_port} "
                    f"IBKR_CLIENT_ID={settings.ibkr_client_id}.{detail}"
                ) from last_exc
        return _ib


def _stock(symbol: str):
    _ensure_event_loop()
    try:
        from ib_insync import Stock
    except Exception as exc:  # noqa: BLE001
        return SimpleNamespace(symbol=symbol.upper(), exchange="SMART", currency="USD")
    return Stock(symbol.upper(), "SMART", "USD")


def _market_order(action: str, qty: float):
    _ensure_event_loop()
    try:
        from ib_insync import MarketOrder
    except Exception as exc:  # noqa: BLE001
        return SimpleNamespace(action=action.upper(), totalQuantity=qty, orderType="MKT", tif="DAY", transmit=True, account=settings.ibkr_account or "")
    return MarketOrder(action.upper(), qty, tif="DAY", transmit=True, account=settings.ibkr_account or "")


def _limit_order(action: str, qty: float, price: float):
    _ensure_event_loop()
    try:
        from ib_insync import LimitOrder
    except Exception as exc:  # noqa: BLE001
        return SimpleNamespace(action=action.upper(), totalQuantity=qty, orderType="LMT", lmtPrice=round(float(price), 2), tif="DAY", transmit=True, account=settings.ibkr_account or "")
    return LimitOrder(action.upper(), qty, round(float(price), 2), tif="DAY", transmit=True, account=settings.ibkr_account or "")


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
    # ``ib.accountSummary()`` can block indefinitely on some Gateway builds with
    # error 321 ("Group name cannot be null"). Use the cached account values that
    # ib_insync maintains after connection; return an empty map rather than
    # hanging the portfolio route if Gateway/account permissions do not publish them.
    account = _account_id(ib)
    try:
        rows = ib.accountValues(account) if account else ib.accountValues()
    except Exception:
        rows = []
    # Multi-currency accounts report monetary tags once per currency *plus* a
    # consolidated row with currency "BASE" (summed into the account base
    # currency). A plain {tag: row} dict keeps whichever currency happens to be
    # last, so cash could reflect a single currency's (possibly negative)
    # balance instead of the total. Prefer the "BASE" row when present so cash
    # and positions reconcile with NetLiquidation.
    summary: dict[str, Any] = {}
    for r in rows or []:
        tag = getattr(r, "tag", "")
        if not tag:
            continue
        if tag not in summary or (getattr(r, "currency", "") or "").upper() == "BASE":
            summary[tag] = r
    return summary


def _get_account_unlocked() -> dict[str, Any]:
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
    if currency.upper() == "BASE":
        currency = "USD"
    if settings.is_paper and not any((equity, cash, buying_power, gross)):
        cash = equity = buying_power = float(settings.paper_starting_cash)
    if settings.is_paper:
        adjustment = float(settings.paper_cash_adjustment or 0.0)
        cash += adjustment
        buying_power += adjustment
        equity += adjustment
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


def _contract_symbol(contract: Any) -> str:
    return str(getattr(contract, "symbol", "") or getattr(contract, "localSymbol", "") or "").upper()


def _filled_qty_price_from_fills(ib: Any) -> dict[str, dict[str, float]]:
    lots: dict[str, dict[str, float]] = {}
    try:
        fills = list(ib.reqExecutions() or [])
    except Exception:
        fills = list(getattr(ib, "fills", lambda: [])() or [])
    for fill in fills:
        contract = getattr(fill, "contract", None)
        exe = getattr(fill, "execution", None)
        symbol = _contract_symbol(contract)
        if not symbol or exe is None:
            continue
        side = enumval(getattr(exe, "side", ""))
        qty = safe_float(getattr(exe, "shares", 0))
        price = safe_float(getattr(exe, "price", 0))
        if not qty or not price:
            continue
        sign = -1.0 if side in {"sld", "sell", "sold"} else 1.0
        row = lots.setdefault(symbol, {"qty": 0.0, "cost": 0.0})
        signed_qty = sign * qty
        row["qty"] += signed_qty
        row["cost"] += signed_qty * price
    return lots


def _rows_from_lots(lots: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for symbol, row in lots.items():
        qty = row["qty"]
        if abs(qty) < 1e-9:
            continue
        avg = abs(row["cost"] / qty) if qty else 0.0
        out.append(_position_row(symbol, qty, avg))
    return out


def _position_row(symbol: str, qty: float, avg: float) -> dict[str, Any]:
    price = get_latest_trade_price(symbol) or avg
    mv = qty * price
    cost = qty * avg
    return {
        "symbol": symbol,
        "qty": qty,
        "qty_available": qty,
        "avg_entry_price": avg,
        "current_price": price,
        "lastday_price": price,
        "market_value": mv,
        "cost_basis": cost,
        "unrealized_pl": mv - cost,
        "unrealized_plpc": ((price - avg) / avg) if avg else 0.0,
        "unrealized_intraday_pl": 0.0,
        "unrealized_intraday_plpc": 0.0,
        "change_today": 0.0,
        "asset_class": "us_equity",
        "exchange": "SMART",
        "side": "long" if qty >= 0 else "short",
    }


def _positions_from_filled_trades(ib: Any) -> list[dict[str, Any]]:
    lots = _filled_qty_price_from_fills(ib)
    for trade in ib.trades() or []:
        order = getattr(trade, "order", None)
        contract = getattr(trade, "contract", None)
        st = getattr(trade, "orderStatus", None)
        state = enumval(getattr(st, "status", ""))
        order_id = str(getattr(order, "orderId", "") or "")
        if state != "filled" or not order_id or order_id == "0":
            continue
        symbol = _contract_symbol(contract)
        if not symbol:
            continue
        qty = safe_float(getattr(st, "filled", 0)) or safe_float(getattr(order, "totalQuantity", 0))
        avg = safe_float(getattr(st, "avgFillPrice", 0))
        if not qty or not avg:
            continue
        sign = 1.0 if enumval(getattr(order, "action", "")) == "buy" else -1.0
        row = lots.setdefault(symbol, {"qty": 0.0, "cost": 0.0})
        # Avoid double-counting if executions already supplied this order.
        if row["qty"] and abs(row["qty"]) >= qty:
            continue
        signed_qty = sign * qty
        row["qty"] += signed_qty
        row["cost"] += signed_qty * avg
    return _rows_from_lots(lots)


def _get_positions_unlocked() -> list[dict[str, Any]]:
    ib = _connect()
    account = _account_id(ib)
    out: list[dict[str, Any]] = []

    # Prefer IBKR's positions feed over ib_insync's portfolio cache. The
    # portfolio cache can retain rows after paper-account resets or flattening
    # fills until the client reconnects, while reqPositions reflects the broker's
    # current open holdings.
    try:
        rows = ib.reqPositions() or []
    except Exception:
        try:
            rows = ib.positions(account) if account else ib.positions()
        except Exception:
            rows = []
    for p in rows:
        c = getattr(p, "contract", None)
        if account and getattr(p, "account", account) != account:
            continue
        sym = _contract_symbol(c)
        qty = safe_float(getattr(p, "position", 0))
        if abs(qty) < 1e-9:
            continue
        avg = safe_float(getattr(p, "avgCost", 0))
        row = _position_row(sym, qty, avg)
        row["exchange"] = getattr(c, "exchange", "SMART") or "SMART"
        out.append(row)
    # Full ib.connect() synchronizes positions/portfolio with the broker. Do not
    # synthesize current positions from session fills here: after a flatten order,
    # a lone SELL fill would otherwise be misread as a new short position even
    # when IBKR reports no open position.
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
    name = sym
    exchange = "SMART"
    try:
        import yfinance as yf

        info = yf.Ticker(sym).get_info() or {}
        name = info.get("longName") or info.get("shortName") or name
        exchange = info.get("exchange") or exchange
    except Exception:
        pass
    return {"symbol": sym, "name": name, "exchange": exchange, "tradable": True, "fractionable": False}


def _quote_from_yfinance(symbol: str) -> dict[str, Any] | None:
    sym = symbol.upper()
    try:
        import yfinance as yf

        ticker = yf.Ticker(sym)
        fast = getattr(ticker, "fast_info", {}) or {}
        price = safe_float(
            fast.get("last_price")
            or fast.get("lastPrice")
            or fast.get("regular_market_price")
            or fast.get("regularMarketPrice")
            or fast.get("previous_close")
            or fast.get("previousClose")
        )
        if not price:
            hist = ticker.history(period="5d", interval="1d", auto_adjust=False)
            if hist is not None and not hist.empty:
                price = safe_float(hist["Close"].dropna().iloc[-1])
        if price:
            return {
                "symbol": sym,
                "bid": 0.0,
                "ask": 0.0,
                "mid": round(price, 4),
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
    except Exception:
        return None
    return None


def _get_latest_quote_unlocked(symbol: str) -> dict[str, Any]:
    fallback = _quote_from_yfinance(symbol)
    if fallback:
        return fallback

    ib = _connect()
    contract = _stock(symbol)
    try:
        qualified = ib.qualifyContracts(contract)
        if qualified:
            contract = qualified[0]
    except Exception:
        pass
    try:
        ib.reqMarketDataType(3)  # delayed data if live market-data entitlements are absent
    except Exception:
        pass
    ticker = ib.reqMktData(contract, "", False, False)
    try:
        ib.sleep(2)
    except Exception:  # noqa: BLE001
        pass
    bid = safe_float(getattr(ticker, "bid", 0))
    ask = safe_float(getattr(ticker, "ask", 0))
    last = safe_float(getattr(ticker, "last", 0))
    close = safe_float(getattr(ticker, "close", 0))
    mid = (bid + ask) / 2 if bid and ask else (bid or ask or last or close)
    try:
        ib.cancelMktData(contract)
    except Exception:
        pass
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


def _empty_bars() -> pd.DataFrame:
    return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])


def _bars_from_yfinance(symbols: list[str], start: dt.datetime | dt.date | str, end: dt.datetime | dt.date | str | None = None, timeframe: str = "1Day") -> dict[str, pd.DataFrame]:
    """Fast no-key historical-data fallback for recommendation scans.

    IBKR historical requests are authoritative but sequential and can take 10–60s
    per symbol when Gateway is slow. A recommendations page that scans many
    symbols must not block on that. Use Yahoo daily/hourly bars for broad scoring
    and keep IBKR for quotes, portfolio and orders.
    """
    if not symbols:
        return {}
    interval = {"1Day": "1d", "1Hour": "1h", "1Min": "1m", "15Min": "15m"}.get(timeframe, "1d")
    try:
        import yfinance as yf
        raw = yf.download(
            tickers=" ".join(dict.fromkeys(s.upper() for s in symbols)),
            start=pd.Timestamp(start).date().isoformat(),
            end=(pd.Timestamp(end).date().isoformat() if end is not None else None),
            interval=interval,
            auto_adjust=False,
            progress=False,
            group_by="ticker",
            threads=True,
            timeout=15,
        )
    except Exception:
        return {}
    out: dict[str, pd.DataFrame] = {}
    if raw is None or raw.empty:
        return out
    for sym in symbols:
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                part = raw[sym.upper()] if sym.upper() in raw.columns.get_level_values(0) else raw[sym]
            else:
                part = raw
            cols = {str(c).lower().replace(" ", "_"): c for c in part.columns}
            df = pd.DataFrame({
                "open": part[cols.get("open")],
                "high": part[cols.get("high")],
                "low": part[cols.get("low")],
                "close": part[cols.get("close")],
                "volume": part[cols.get("volume")],
            }).dropna(subset=["open", "high", "low", "close"])
            if not df.empty:
                out[sym.upper()] = df[["open", "high", "low", "close", "volume"]]
        except Exception:
            continue
    return out


def _get_bars_unlocked(symbol: str, start: dt.datetime | dt.date | str, end: dt.datetime | dt.date | str | None = None, timeframe: str = "1Day") -> pd.DataFrame:
    fallback = _bars_from_yfinance([symbol], start, end, timeframe).get(symbol.upper())
    if fallback is not None and not fallback.empty:
        return fallback

    ib = _connect()
    bar_size = {"1Day": "1 day", "1Hour": "1 hour", "1Min": "1 min", "15Min": "15 mins"}.get(timeframe, "1 day")
    end_dt = "" if end is None else pd.Timestamp(end).strftime("%Y%m%d %H:%M:%S")
    contract = _stock(symbol)
    try:
        qualified = ib.qualifyContracts(contract)
        if qualified:
            contract = qualified[0]
    except Exception:
        pass
    try:
        bars = ib.reqHistoricalData(
            contract,
            endDateTime=end_dt,
            durationStr=_duration(start, end),
            barSizeSetting=bar_size,
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1,
            timeout=10,
        )
    except Exception:
        bars = []
    rows = [{"timestamp": pd.Timestamp(b.date), "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume} for b in bars or []]
    if rows:
        return pd.DataFrame(rows).set_index("timestamp")[["open", "high", "low", "close", "volume"]]
    return _bars_from_yfinance([symbol], start, end, timeframe).get(symbol.upper(), _empty_bars())


def get_bars_multi(symbols: list[str], start: dt.datetime | dt.date | str, end: dt.datetime | dt.date | str | None = None, timeframe: str = "1Day") -> dict[str, pd.DataFrame]:
    out = _bars_from_yfinance(symbols, start, end, timeframe)
    missing = [s for s in symbols if s.upper() not in out]
    for s in missing[:10]:  # bounded IBKR fallback; avoid page-load hangs on broad scans
        try:
            df = get_bars(s, start, end, timeframe)
        except Exception:
            continue
        if not df.empty:
            out[s.upper()] = df
    return out



def _price_or_none(value: Any) -> float | None:
    price = safe_float(value)
    # ib_insync uses DBL_MAX for unset limit/aux prices.
    if not price or price > 1e20:
        return None
    return price


def _trade_log_messages(trade: Any) -> list[str]:
    messages: list[str] = []
    for entry in getattr(trade, "log", []) or []:
        status = enumval(getattr(entry, "status", ""))
        message = str(getattr(entry, "message", "") or "").strip()
        code = getattr(entry, "errorCode", None)
        parts = [p for p in (status, f"{code}" if code else "", message) if p]
        if parts:
            messages.append(" · ".join(parts))
    return messages[-5:]


def _local_order_submitted_at(order_ids: set[str]) -> dict[str, str]:
    if not order_ids:
        return {}
    try:
        with SessionLocal() as db:
            rows = db.scalars(
                select(OrderRecord).where(OrderRecord.alpaca_order_id.in_(order_ids))
            ).all()
    except Exception:
        return {}
    return {
        str(row.alpaca_order_id): row.created_at.isoformat()
        for row in rows
        if row.alpaca_order_id and row.created_at
    }


def _local_order_submitted_at_by_details() -> tuple[
    dict[tuple[str, str, float], str],
    dict[tuple[str, str], str],
]:
    try:
        with SessionLocal() as db:
            rows = db.scalars(select(OrderRecord)).all()
    except Exception:
        return {}, {}

    by_qty: dict[tuple[str, str, float], str] = {}
    by_symbol_side_rows: dict[tuple[str, str], list[OrderRecord]] = {}
    for row in rows:
        if not row.created_at:
            continue
        symbol = row.symbol.upper()
        side = row.side.lower()
        by_qty[(symbol, side, float(row.qty or 0))] = row.created_at.isoformat()
        by_symbol_side_rows.setdefault((symbol, side), []).append(row)

    by_unique_symbol_side = {
        key: matches[0].created_at.isoformat()
        for key, matches in by_symbol_side_rows.items()
        if len(matches) == 1
    }
    return by_qty, by_unique_symbol_side


def _why_pending(state: str, order_type: str) -> str | None:
    st = state.lower()
    if st == "pendingsubmit":
        return "Order is still pending submission in IBKR/TWS. Check TWS API/order prompts, account permissions, and whether the order needs manual transmission."
    if st == "presubmitted":
        return "Order is accepted by IBKR but not yet active at the exchange."
    if st == "submitted" and order_type.lower() in {"mkt", "market"}:
        return "Market order is submitted and waiting for IBKR fill confirmation."
    return None


def _submit_order_unlocked(symbol: str, qty: float, side: str, order_type: str = "market", limit_price: float | None = None, stop_loss: float | None = None, take_profit: float | None = None, confirm_live: bool = False) -> dict[str, Any]:
    _require_order_enabled(confirm_live)
    ib = _connect()
    action = "BUY" if side.lower() == "buy" else "SELL"
    order = _limit_order(action, qty, limit_price) if order_type == "limit" and limit_price is not None else _market_order(action, qty)
    # Stop-loss/take-profit bracket support is intentionally conservative in the
    # first IBKR adapter: risk math is preserved, but unsupported child legs are
    # not synthesized until covered by integration testing against a paper TWS.
    contract = _stock(symbol)
    try:
        qualified = ib.qualifyContracts(contract)
        if qualified:
            contract = qualified[0]
    except Exception:
        pass
    trade = ib.placeOrder(contract, order)
    try:
        ib.sleep(1.0)
    except Exception:
        pass
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


def _cancel_order_unlocked(order_id: str) -> None:
    ib = _connect()
    target = None
    try:
        ib.reqOpenOrders()
        ib.sleep(0.5)
    except Exception:
        pass
    for trade in ib.trades() or []:
        if str(getattr(getattr(trade, "order", None), "orderId", "")) == str(order_id):
            target = trade
            break
    if target is None:
        raise BrokerUnavailable(f"IBKR order {order_id} was not found in open trades.")
    ib.cancelOrder(target.order)
    for _ in range(20):
        try:
            ib.sleep(0.5)
        except Exception:
            break
        state = enumval(getattr(getattr(target, "orderStatus", None), "status", ""))
        if state in {"cancelled", "apicancelled", "inactive"}:
            return
    # Return after sending the cancellation even if IBKR is still reporting
    # PendingCancel; callers can refresh /orders to observe the final state.
    return


def replace_order(order_id: str, *, stop_price: float | None = None, limit_price: float | None = None) -> dict[str, Any]:
    raise BrokerUnavailable("IBKR order replace is not available through this adapter yet; cancel and resubmit instead.")


def _close_position_unlocked(symbol: str, confirm_live: bool = False) -> dict[str, Any]:
    _require_order_enabled(confirm_live)
    sym = symbol.upper()
    pos = next((p for p in _get_positions_unlocked() if p["symbol"] == sym), None)
    if not pos:
        raise BrokerUnavailable(f"No IBKR position found for {sym}.")
    side = "sell" if float(pos["qty"]) > 0 else "buy"
    return submit_order(sym, abs(float(pos["qty"])), side, confirm_live=confirm_live)


def _list_orders_unlocked(status: str = "all", limit: int = 50) -> list[dict[str, Any]]:
    ib = _connect()
    broker_open_order_ids: set[str] = set()
    try:
        ib.reqOpenOrders()
        ib.sleep(0.5)
        broker_open_order_ids = {
            str(getattr(order, "orderId", ""))
            for order in (ib.openOrders() or [])
            if str(getattr(order, "orderId", ""))
        }
    except Exception:
        pass
    out: list[dict[str, Any]] = []
    trades = list(ib.trades() or [])
    order_ids = {
        str(getattr(getattr(trade, "order", None), "orderId", ""))
        for trade in trades[-limit:]
    }
    submitted_at_by_id = _local_order_submitted_at({oid for oid in order_ids if oid and oid != "0"})
    submitted_at_by_details, submitted_at_by_unique_symbol_side = _local_order_submitted_at_by_details()
    for trade in trades[-limit:]:
        order = getattr(trade, "order", None)
        contract = getattr(trade, "contract", None)
        st = getattr(trade, "orderStatus", None)
        state = enumval(getattr(st, "status", ""))
        terminal_states = {"filled", "cancelled", "apicancelled", "inactive", "pendingcancel"}
        order_id = str(getattr(order, "orderId", ""))
        if status == "open" and (state in terminal_states or order_id not in broker_open_order_ids):
            continue
        if status == "closed" and state not in terminal_states:
            continue
        order_type = enumval(getattr(order, "orderType", ""))
        qty = safe_float(getattr(order, "totalQuantity", 0))
        filled_qty = safe_float(getattr(st, "filled", 0))
        remaining_qty = safe_float(getattr(st, "remaining", 0))
        if state not in {"filled", "cancelled", "inactive"} and remaining_qty <= 0 and filled_qty < qty:
            remaining_qty = max(0.0, qty - filled_qty)
        log_messages = _trade_log_messages(trade)
        symbol = getattr(contract, "symbol", "")
        side = enumval(getattr(order, "action", ""))
        submitted_at = submitted_at_by_id.get(order_id)
        if submitted_at is None:
            detail_key = (symbol.upper(), side.lower(), qty)
            submitted_at = submitted_at_by_details.get(detail_key)
        if submitted_at is None:
            submitted_at = submitted_at_by_unique_symbol_side.get((symbol.upper(), side.lower()))
        out.append({
            "id": order_id,
            "broker_order_id": order_id,
            "symbol": symbol,
            "qty": qty,
            "filled_qty": filled_qty,
            "remaining_qty": remaining_qty,
            "filled_avg_price": safe_float(getattr(st, "avgFillPrice", 0)) or None,
            "side": side,
            "type": order_type,
            "order_class": "",
            "time_in_force": getattr(order, "tif", "DAY") or "DAY",
            "limit_price": _price_or_none(getattr(order, "lmtPrice", 0)),
            "stop_price": _price_or_none(getattr(order, "auxPrice", 0)),
            "status": state,
            "status_detail": log_messages[-1] if log_messages else None,
            "pending_reason": _why_pending(state, order_type),
            "log": log_messages,
            "extended_hours": False,
            "submitted_at": submitted_at,
            "filled_at": None,
        })
    return out


def get_activities(activity_types: str | None = None, page_size: int = 100) -> list[dict[str, Any]]:
    with _ib_op_lock:
        ib = _connect()
        try:
            fills = list(ib.reqExecutions() or [])
        except Exception:
            fills = list(getattr(ib, "fills", lambda: [])() or [])
        out: list[dict[str, Any]] = []
        allowed = {s.strip().upper() for s in activity_types.split(",")} if activity_types else set()
        for fill in fills[-page_size:]:
            contract = getattr(fill, "contract", None)
            exe = getattr(fill, "execution", None)
            report = getattr(fill, "commissionReport", None)
            symbol = _contract_symbol(contract)
            side_raw = enumval(getattr(exe, "side", "")) if exe else ""
            side = "buy" if side_raw in {"bot", "buy", "bought"} else "sell" if side_raw in {"sld", "sell", "sold"} else side_raw
            qty = safe_float(getattr(exe, "shares", 0)) if exe else 0.0
            price = safe_float(getattr(exe, "price", 0)) if exe else 0.0
            commission = safe_float(getattr(report, "commission", 0)) if report else 0.0
            net = qty * price * (-1 if side == "buy" else 1) - commission
            when = getattr(exe, "time", None) if exe else None
            if allowed and "FILL" not in allowed and "TRADE" not in allowed:
                continue
            out.append({
                "id": str(getattr(exe, "execId", "") or getattr(exe, "orderId", "") or len(out)),
                "activity_type": "FILL",
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "cum_qty": qty,
                "leaves_qty": 0.0,
                "price": price,
                "net_amount": net,
                "order_status": "filled",
                "description": f"{side.upper()} {qty:g} {symbol} @ {price:g}" if symbol else "Execution fill",
                "date": when.isoformat() if hasattr(when, "isoformat") else None,
            })
        out.sort(key=lambda x: x.get("date") or "", reverse=True)
        return out[:page_size]


def _get_portfolio_history_unlocked(period: str = "1M", timeframe: str = "1D") -> dict[str, Any]:
    acct = _get_account_unlocked()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    equity = acct["equity"]
    return {"period": period, "timeframe": timeframe, "base_value": equity, "points": [{"time": now, "equity": equity, "profit_loss": 0.0, "profit_loss_pct": 0.0}], "total_pl": 0.0, "total_pl_pct": 0.0}


def get_account() -> dict[str, Any]:
    with _ib_op_lock:
        return _get_account_unlocked()


def get_positions() -> list[dict[str, Any]]:
    with _ib_op_lock:
        return _get_positions_unlocked()


def get_latest_quote(symbol: str) -> dict[str, Any]:
    with _ib_op_lock:
        return _get_latest_quote_unlocked(symbol)


def get_bars(symbol: str, start: dt.datetime | dt.date | str, end: dt.datetime | dt.date | str | None = None, timeframe: str = "1Day") -> pd.DataFrame:
    with _ib_op_lock:
        return _get_bars_unlocked(symbol, start, end, timeframe)


def submit_order(symbol: str, qty: float, side: str, order_type: str = "market", limit_price: float | None = None, stop_loss: float | None = None, take_profit: float | None = None, confirm_live: bool = False) -> dict[str, Any]:
    with _ib_op_lock:
        return _submit_order_unlocked(symbol, qty, side, order_type, limit_price, stop_loss, take_profit, confirm_live)


def cancel_order(order_id: str) -> None:
    with _ib_op_lock:
        return _cancel_order_unlocked(order_id)


def close_position(symbol: str, confirm_live: bool = False) -> dict[str, Any]:
    with _ib_op_lock:
        return _close_position_unlocked(symbol, confirm_live)


def list_orders(status: str = "all", limit: int = 50) -> list[dict[str, Any]]:
    with _ib_op_lock:
        return _list_orders_unlocked(status, limit)


def get_portfolio_history(period: str = "1M", timeframe: str = "1D") -> dict[str, Any]:
    with _ib_op_lock:
        return _get_portfolio_history_unlocked(period, timeframe)

def get_news(symbols: list[str], limit: int = 20, include_external: bool = False) -> list[dict[str, Any]]:
    """Best-effort no-key Yahoo Finance news fallback for sentiment.

    ``limit`` is applied per symbol. The recommender asks for a broad universe in
    one call; treating ``limit`` as a global cap meant the first few symbols got
    all headlines while the rest saw empty news and neutral sentiment.
    """
    out: list[dict[str, Any]] = []
    per_symbol_limit = max(1, int(limit or 20))
    try:
        import yfinance as yf
    except Exception:  # noqa: BLE001
        return []
    for symbol in symbols:
        sym = symbol.upper()
        try:
            rows = getattr(yf.Ticker(sym), "news", None) or []
        except Exception:  # noqa: BLE001
            continue
        symbol_count = 0
        for n in rows:
            if symbol_count >= per_symbol_limit:
                break
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
                "symbols": [sym],
                "source": provider.get("displayName") if isinstance(provider, dict) else "Yahoo Finance",
                "url": click.get("url") if isinstance(click, dict) else data.get("link") or "",
                "created_at": created.isoformat() if created else None,
            })
            symbol_count += 1
    return out


def get_most_actives(top: int = 100, by: str = "volume") -> list[str]:
    """Best-effort most-active US stock universe for IBKR installs.

    IBKR does not expose the Alpaca screener API this app originally used, so
    use Yahoo Finance's no-key predefined screener. If Yahoo is unavailable,
    fall back to the curated core liquid universe instead of collapsing the scan
    to the user's watchlist only.
    """
    limit = max(1, min(int(top or 100), 250))
    try:
        import yfinance as yf

        response = yf.screen("most_actives", count=limit)
        quotes = response.get("quotes", []) if isinstance(response, dict) else []
        symbols = []
        for quote in quotes:
            symbol = str(quote.get("symbol") or "").strip().upper()
            quote_type = str(quote.get("quoteType") or "").upper()
            if not symbol or quote_type not in {"EQUITY", ""}:
                continue
            if symbol.startswith("^") or "." in symbol:
                continue
            symbols.append(symbol)
        if symbols:
            return list(dict.fromkeys(symbols))[:limit]
    except Exception:  # noqa: BLE001 — screener is best-effort
        pass

    from ..strategies.data.universe import CORE_LIQUID_UNIVERSE

    return CORE_LIQUID_UNIVERSE[:limit]


def sync_watchlist(symbols: list[str], name: str = "StockSim") -> dict[str, Any]:
    return {"symbols": [s.strip().upper() for s in symbols if s.strip()], "action": "noop"}
