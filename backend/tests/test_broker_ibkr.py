import importlib
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


def test_config_defaults_are_ibkr_and_safe():
    from app.config import Settings

    s = Settings(_env_file=None)
    assert s.broker == "ibkr"
    assert s.ibkr_host == "127.0.0.1"
    assert s.ibkr_port == 4002
    assert s.ibkr_client_id == 11
    assert s.ibkr_account == ""
    assert s.ibkr_trading_mode == "paper"
    assert s.trading_enabled is False
    assert s.live_trading is False
    assert s.is_paper is True
    assert s.has_credentials is True


def test_broker_facade_imports_without_ib_insync(monkeypatch):
    monkeypatch.setitem(sys.modules, "ib_insync", None)
    mod = importlib.reload(importlib.import_module("app.broker_client"))
    assert mod.BrokerUnavailable
    assert callable(mod.get_account)


def test_ibkr_connection_is_lazy_and_maps_account(monkeypatch):
    from app.brokers import ibkr

    ib = Mock()
    ib.isConnected.return_value = False
    ib.managedAccounts.return_value = ["DU123"]
    ib.accountValues.return_value = [
        SimpleNamespace(account="DU123", tag="NetLiquidation", value="100000", currency="USD"),
        SimpleNamespace(account="DU123", tag="TotalCashValue", value="50000", currency="USD"),
        SimpleNamespace(account="DU123", tag="BuyingPower", value="200000", currency="USD"),
        SimpleNamespace(account="DU123", tag="GrossPositionValue", value="10000", currency="USD"),
    ]
    monkeypatch.setattr(ibkr, "_ib", ib)

    account = ibkr.get_account()

    ib.connect.assert_called_once()
    assert account["account_number"] == "DU123"
    assert account["equity"] == 100000.0
    assert account["cash"] == 50000.0
    assert account["buying_power"] == 200000.0
    assert account["is_paper"] is True


def test_ibkr_submit_order_requires_app_trading_enabled(monkeypatch):
    from app.brokers import ibkr

    monkeypatch.setattr(ibkr.settings, "trading_enabled", False)
    with pytest.raises(ibkr.BrokerUnavailable, match="TRADING_ENABLED"):
        ibkr.submit_order("AAPL", 1, "buy")


def test_ibkr_live_orders_require_confirm_live(monkeypatch):
    from app.brokers import ibkr

    monkeypatch.setattr(ibkr.settings, "trading_enabled", True)
    monkeypatch.setattr(ibkr.settings, "ibkr_trading_mode", "live")
    monkeypatch.setattr(ibkr.settings, "live_trading", True)
    with pytest.raises(ibkr.BrokerUnavailable, match="confirm_live"):
        ibkr.submit_order("AAPL", 1, "buy")


def test_ibkr_submit_order_maps_trade_without_real_ib(monkeypatch):
    from app.brokers import ibkr

    order = SimpleNamespace(orderId=42, action="BUY", totalQuantity=3, orderType="MKT", lmtPrice=0, auxPrice=0)
    trade = SimpleNamespace(
        order=order,
        orderStatus=SimpleNamespace(status="Submitted", filled=0, avgFillPrice=0),
        contract=SimpleNamespace(symbol="AAPL"),
        log=[],
    )
    ib = Mock()
    ib.placeOrder.return_value = trade
    monkeypatch.setattr(ibkr, "_connect", lambda: ib)
    monkeypatch.setattr(ibkr.settings, "trading_enabled", True)
    monkeypatch.setattr(ibkr.settings, "ibkr_trading_mode", "paper")

    result = ibkr.submit_order("AAPL", 3, "buy")

    assert result["broker_order_id"] == "42"
    assert result["alpaca_order_id"] == "42"
    assert result["symbol"] == "AAPL"
    assert result["qty"] == 3.0
    assert result["side"] == "buy"
    assert result["status"] == "submitted"


def test_ibkr_bars_multi_prefers_batch_fallback_and_bounds_ibkr_calls(monkeypatch):
    from app.brokers import ibkr

    symbols = [f"SYM{i}" for i in range(12)]
    monkeypatch.setattr(ibkr, "_bars_from_yfinance", lambda symbols, start, end=None, timeframe="1Day": {"SYM0": ibkr._empty_bars()})
    called: list[str] = []

    def fake_get_bars(symbol, start, end=None, timeframe="1Day"):
        called.append(symbol)
        raise ibkr.BrokerUnavailable("IBKR unavailable")

    monkeypatch.setattr(ibkr, "get_bars", fake_get_bars)

    out = ibkr.get_bars_multi(symbols, "2024-01-01", "2024-01-31")

    assert list(out) == ["SYM0"]
    assert called == symbols[1:11]


def test_scheduler_cycle_lock_returns_in_progress_without_running(monkeypatch):
    from app.services import scheduler

    ran = False

    def fail_if_called(*args, **kwargs):
        nonlocal ran
        ran = True
        raise AssertionError("recommendations should not run when another cycle is active")

    monkeypatch.setattr(scheduler.recommender, "generate", fail_if_called)
    scheduler._cycle_lock.acquire()
    try:
        assert scheduler.run_cycle(force=True) == {"skipped": "cycle already running"}
    finally:
        scheduler._cycle_lock.release()
    assert ran is False


def test_sync_watchlist_is_noop():
    from app import broker_client as broker

    assert broker.sync_watchlist(["aapl"]) == {"symbols": ["AAPL"], "action": "noop"}
