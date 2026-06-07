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
    assert s.paper_cash_adjustment == 0.0
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
    monkeypatch.setattr(ibkr.settings, "paper_cash_adjustment", 0.0)

    account = ibkr.get_account()

    ib.connect.assert_called_once()
    assert account["account_number"] == "DU123"
    assert account["equity"] == 100000.0
    assert account["cash"] == 50000.0
    assert account["buying_power"] == 200000.0
    assert account["is_paper"] is True


def test_ibkr_connect_disables_multi_account_group_request(monkeypatch):
    from app.brokers import ibkr

    ib = Mock()
    ib.isConnected.return_value = False
    monkeypatch.setattr(ibkr, "_ib", None)
    monkeypatch.setattr(ibkr, "_ib_class", lambda: lambda: ib)
    monkeypatch.setattr(ibkr.settings, "ibkr_account", "DU123")

    out = ibkr._connect()

    assert out is ib
    assert ib.MaxSyncedSubAccounts == 0
    ib.connect.assert_called_once_with(
        ibkr.settings.ibkr_host,
        ibkr.settings.ibkr_port,
        clientId=ibkr.settings.ibkr_client_id,
        timeout=5,
    )


def test_ibkr_multi_currency_cash_uses_consolidated_base_row(monkeypatch):
    """Cash must reflect the consolidated BASE total, not a single currency line.

    A multi-currency account reports TotalCashValue once per currency plus a
    "BASE" consolidated row. A negative USD cash line must not shadow the
    positive base-currency total, or cash won't reconcile with NetLiquidation.
    """
    from app.brokers import ibkr

    ib = Mock()
    ib.managedAccounts.return_value = ["DU123"]
    ib.accountValues.return_value = [
        SimpleNamespace(account="DU123", tag="NetLiquidation", value="98087.74", currency="USD"),
        SimpleNamespace(account="DU123", tag="GrossPositionValue", value="78731.07", currency="USD"),
        # Consolidated cash first, then a single-currency line that must NOT win.
        SimpleNamespace(account="DU123", tag="TotalCashValue", value="19356.67", currency="BASE"),
        SimpleNamespace(account="DU123", tag="TotalCashValue", value="-3400.27", currency="USD"),
    ]
    monkeypatch.setattr(ibkr, "_connect", lambda: ib)
    monkeypatch.setattr(ibkr.settings, "ibkr_trading_mode", "paper")
    monkeypatch.setattr(ibkr.settings, "paper_cash_adjustment", 0.0)

    account = ibkr.get_account()

    assert account["cash"] == 19356.67
    assert account["portfolio_value"] == 98087.74
    assert account["position_market_value"] == 78731.07
    # positions + cash reconcile with net liquidation value
    assert round(account["position_market_value"] + account["cash"], 2) == account["portfolio_value"]


def test_ibkr_paper_cash_adjustment_adds_to_account(monkeypatch):
    from app.brokers import ibkr

    ib = Mock()
    ib.managedAccounts.return_value = ["DU123"]
    ib.accountValues.return_value = [
        SimpleNamespace(account="DU123", tag="NetLiquidation", value="100000", currency="USD"),
        SimpleNamespace(account="DU123", tag="TotalCashValue", value="50000", currency="USD"),
        SimpleNamespace(account="DU123", tag="BuyingPower", value="200000", currency="USD"),
        SimpleNamespace(account="DU123", tag="GrossPositionValue", value="10000", currency="USD"),
    ]
    monkeypatch.setattr(ibkr, "_connect", lambda: ib)
    monkeypatch.setattr(ibkr.settings, "ibkr_trading_mode", "paper")
    monkeypatch.setattr(ibkr.settings, "paper_cash_adjustment", 900000.0)

    account = ibkr.get_account()

    assert account["equity"] == 1000000.0
    assert account["cash"] == 950000.0
    assert account["buying_power"] == 1100000.0
    assert account["portfolio_value"] == 1000000.0


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


def test_scheduler_cycle_publishes_refresh_message(monkeypatch):
    from app.services import scheduler

    monkeypatch.setattr(scheduler, "settings", SimpleNamespace(has_credentials=True))
    monkeypatch.setattr(scheduler.runtime_settings, "get", lambda key: False)
    monkeypatch.setattr(scheduler.proposals, "expire_stale", lambda: None)
    monkeypatch.setattr(scheduler.proposals, "build_from_reco", lambda reco: [])
    monkeypatch.setattr(scheduler.proposals, "confirm_all", lambda: {"results": []})

    def fake_generate(persist=True):
        return {
            "recommendations": [],
            "top_buys": [],
            "top_sells": [],
            "generated_at": None,
            "regime": None,
            "configured": True,
            "message": "Refresh completed, but no historical market data was available.",
            "errors": {"AAPL": "no bars"},
        }

    monkeypatch.setattr(scheduler.recommender, "generate", fake_generate)

    result = scheduler.run_cycle(force=True)

    assert result["recommendations"] == 0
    assert scheduler.LATEST["refresh_status"] == "complete"
    assert scheduler.LATEST["message"] == "Refresh completed, but no historical market data was available."
    assert scheduler.LATEST["errors"] == {"AAPL": "no bars"}


def test_scheduler_cycle_executes_auto_trade_when_enabled(monkeypatch):
    from app.services import scheduler

    monkeypatch.setattr(scheduler, "settings", SimpleNamespace(has_credentials=True))
    monkeypatch.setattr(scheduler.runtime_settings, "get", lambda key: key == "auto_trade")
    monkeypatch.setattr(scheduler.proposals, "expire_stale", lambda: None)

    built: list[dict[str, object]] = []
    confirmed = False

    def fake_build(reco):
        built.append(reco)
        return [{"id": 1, "symbol": "AMD", "side": "buy"}]

    def fake_confirm_all():
        nonlocal confirmed
        confirmed = True
        return {"results": [{"proposal_id": 1, "symbol": "AMD", "side": "buy", "ok": True}]}

    monkeypatch.setattr(scheduler.proposals, "build_from_reco", fake_build)
    monkeypatch.setattr(scheduler.proposals, "confirm_all", fake_confirm_all)
    monkeypatch.setattr(
        scheduler.recommender,
        "generate",
        lambda persist=True: {
            "recommendations": [{"symbol": "AMD", "action": "BUY"}],
            "top_buys": [{"symbol": "AMD"}],
            "top_sells": [],
            "generated_at": "now",
            "regime": {"label": "risk_on"},
            "configured": True,
            "message": None,
            "errors": {},
        },
    )

    result = scheduler.run_cycle(force=True)

    assert len(built) == 1
    assert confirmed is True
    assert result["proposals"] == 1
    assert result["executed"] == 1
    assert result["execution_errors"] == 0


def test_paper_snapshot_preserves_broker_account_values(monkeypatch):
    from app.services import portfolio

    monkeypatch.setattr(
        portfolio,
        "settings",
        SimpleNamespace(
            has_credentials=True,
            is_paper=True,
            paper_starting_cash=100000.0,
            paper_cash_adjustment=900000.0,
        ),
    )
    monkeypatch.setattr(
        portfolio.ac,
        "get_account",
        lambda: {
            "cash": 1000000.0,
            "buying_power": 1000000.0,
            "equity": 1000000.0,
            "last_equity": 1000000.0,
            "portfolio_value": 1000000.0,
            "long_market_value": 0.0,
            "short_market_value": 0.0,
            "position_market_value": 0.0,
            "regt_buying_power": 1000000.0,
            "daytrading_buying_power": 1000000.0,
        },
    )
    monkeypatch.setattr(
        portfolio.ac,
        "get_positions",
        lambda: [
            {"symbol": "AAPL", "market_value": 120000.0, "cost_basis": 100000.0},
            {"symbol": "MSFT", "market_value": 45000.0, "cost_basis": 50000.0},
        ],
    )

    snap = portfolio.snapshot()

    assert snap["account"]["cash"] == 1000000.0
    assert snap["account"]["buying_power"] == 1000000.0
    assert snap["account"]["equity"] == 1000000.0
    assert snap["account"]["portfolio_value"] == 1000000.0
    assert snap["account"]["position_market_value"] == 0.0


def test_sync_watchlist_is_noop():
    from app import broker_client as broker

    assert broker.sync_watchlist(["aapl"]) == {"symbols": ["AAPL"], "action": "noop"}


def test_ibkr_open_orders_hides_pending_cancel_stale_trade(monkeypatch):
    from app.brokers import ibkr

    order = SimpleNamespace(orderId=272, action="BUY", totalQuantity=1, orderType="LMT", lmtPrice=1.0, auxPrice=0, tif="DAY")
    trade = SimpleNamespace(
        order=order,
        orderStatus=SimpleNamespace(status="PendingCancel", filled=0, remaining=1, avgFillPrice=0),
        contract=SimpleNamespace(symbol="SPY"),
        log=[],
    )
    ib = Mock()
    ib.trades.return_value = [trade]
    ib.openOrders.return_value = [order]
    monkeypatch.setattr(ibkr, "_connect", lambda: ib)

    assert ibkr.list_orders(status="open") == []
    assert ibkr.list_orders(status="closed")[0]["status"] == "pendingcancel"


def test_ibkr_open_orders_require_broker_open_order(monkeypatch):
    from app.brokers import ibkr

    order = SimpleNamespace(orderId=587, action="SELL", totalQuantity=347, orderType="MKT", lmtPrice=0, auxPrice=0, tif="DAY")
    trade = SimpleNamespace(
        order=order,
        orderStatus=SimpleNamespace(status="PendingSubmit", filled=0, remaining=347, avgFillPrice=0),
        contract=SimpleNamespace(symbol="AAPL"),
        log=[],
    )
    ib = Mock()
    ib.trades.return_value = [trade]
    ib.openOrders.return_value = []
    monkeypatch.setattr(ibkr, "_connect", lambda: ib)

    assert ibkr.list_orders(status="open") == []
