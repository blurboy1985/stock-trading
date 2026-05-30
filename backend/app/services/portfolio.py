"""Portfolio snapshot + risk-gated order placement.

Order flow: risk.validate_order -> live-trading safety gate -> Alpaca submit ->
persist a local OrderRecord. Alpaca remains the source of truth for fills.
"""
from __future__ import annotations

from typing import Any

from .. import alpaca_client as ac
from ..config import settings
from ..db import SessionLocal
from ..models import OrderRecord
from . import risk


class OrderRejected(Exception):
    """Raised when an order fails a risk check or the live-trading gate."""


def snapshot() -> dict[str, Any]:
    """Account + positions, or a clear 'not configured' payload."""
    if not settings.has_credentials:
        return {
            "configured": False,
            "message": "Alpaca credentials not set — add them in backend/.env.",
            "account": None,
            "positions": [],
        }
    account = ac.get_account()
    positions = ac.get_positions()
    return {"configured": True, "account": account, "positions": positions}


def _live_gate(confirm_live: bool) -> bool:
    """True if real-money trading is fully authorized for this order.

    Requires ALL of: env LIVE_TRADING=true, a non-paper endpoint, and an
    explicit per-order confirmation from the caller (UI). Paper trading always
    passes (no real money at stake).
    """
    if settings.is_paper:
        return True
    return settings.live_trading and confirm_live


def place_order(
    symbol: str,
    side: str,
    qty: float | None = None,
    order_type: str = "market",
    limit_price: float | None = None,
    source: str = "manual",
    confirm_live: bool = False,
) -> dict[str, Any]:
    """Validate, gate, submit, and record an order. Raises OrderRejected."""
    symbol = symbol.upper()
    snap = snapshot()
    if not snap["configured"]:
        raise OrderRejected("Alpaca credentials not configured.")
    account, positions = snap["account"], snap["positions"]

    # Reference price for sizing / risk math.
    price = limit_price or ac.get_latest_quote(symbol)["mid"]
    if not price:
        raise OrderRejected(f"could not determine a price for {symbol}")

    # Auto-size if qty omitted (used by auto-trader / one-click buy).
    if qty is None:
        cfg = risk.runtime_settings.get_all()
        qty = risk.size_position(
            float(account["equity"]), price, cfg["max_position_pct"]
        )

    decision = risk.validate_order(account, positions, symbol, side, qty, price)
    if not decision.ok:
        raise OrderRejected(decision.reason)

    if not _live_gate(confirm_live):
        raise OrderRejected(
            "Live trading is not authorized. Real-money orders require "
            "LIVE_TRADING=true, a live endpoint, and explicit confirmation."
        )

    result = ac.submit_order(
        symbol=symbol,
        qty=decision.qty,
        side=side,
        order_type=order_type,
        limit_price=limit_price,
        stop_loss=decision.stop_loss,
        take_profit=decision.take_profit,
    )

    with SessionLocal() as db:
        db.add(
            OrderRecord(
                alpaca_order_id=result.get("alpaca_order_id"),
                symbol=symbol,
                side=side.lower(),
                qty=decision.qty,
                order_type=order_type,
                limit_price=limit_price,
                stop_loss=decision.stop_loss,
                take_profit=decision.take_profit,
                status=result.get("status", "new"),
                is_paper=settings.is_paper,
                source=source,
            )
        )
        db.commit()

    return {
        "submitted": True,
        "order": result,
        "stop_loss": decision.stop_loss,
        "take_profit": decision.take_profit,
        "is_paper": settings.is_paper,
    }


def close_position(
    symbol: str, source: str = "manual", confirm_live: bool = False
) -> dict[str, Any]:
    """Flatten a held position at market (cancels its open bracket first).

    Goes through the same live-trading gate as ``place_order`` — paper always
    passes; real-money liquidation still needs the full live authorization.
    """
    symbol = symbol.upper()
    snap = snapshot()
    if not snap["configured"]:
        raise OrderRejected("Alpaca credentials not configured.")

    held = next((p for p in snap["positions"] if p["symbol"] == symbol), None)
    if not held or float(held["qty"]) <= 0:
        raise OrderRejected(f"no open position in {symbol}")

    if not _live_gate(confirm_live):
        raise OrderRejected(
            "Live trading is not authorized. Real-money orders require "
            "LIVE_TRADING=true, a live endpoint, and explicit confirmation."
        )

    result = ac.close_position(symbol)

    with SessionLocal() as db:
        db.add(
            OrderRecord(
                alpaca_order_id=result.get("alpaca_order_id"),
                symbol=symbol,
                side="sell",
                qty=float(held["qty"]),
                order_type="market",
                status=result.get("status", "new"),
                is_paper=settings.is_paper,
                source=source,
            )
        )
        db.commit()

    return {"submitted": True, "order": result, "is_paper": settings.is_paper}
