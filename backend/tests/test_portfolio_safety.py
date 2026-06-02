import pytest


def test_place_order_rejects_when_trading_disabled_before_broker_snapshot(monkeypatch):
    from app.services import portfolio

    monkeypatch.setattr(portfolio.settings, "trading_enabled", False)

    def fail_snapshot():
        raise AssertionError("snapshot/broker access should not be reached when trading is disabled")

    monkeypatch.setattr(portfolio, "snapshot", fail_snapshot)

    with pytest.raises(portfolio.OrderRejected, match="TRADING_ENABLED=true"):
        portfolio.place_order("AAPL", "buy", qty=1)


def test_close_position_rejects_when_trading_disabled_before_broker_snapshot(monkeypatch):
    from app.services import portfolio

    monkeypatch.setattr(portfolio.settings, "trading_enabled", False)

    def fail_snapshot():
        raise AssertionError("snapshot/broker access should not be reached when trading is disabled")

    monkeypatch.setattr(portfolio, "snapshot", fail_snapshot)

    with pytest.raises(portfolio.OrderRejected, match="TRADING_ENABLED=true"):
        portfolio.close_position("AAPL")
