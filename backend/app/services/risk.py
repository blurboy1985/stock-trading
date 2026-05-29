"""Pre-trade risk checks and position sizing.

Every order — manual, auto, paper, or live — must pass ``validate_order`` before
reaching Alpaca. This is the single chokepoint enforcing position-size caps,
total-exposure caps, and buying-power limits, and it computes the protective
stop-loss / take-profit bracket.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import runtime_settings


@dataclass
class RiskDecision:
    ok: bool
    reason: str = ""
    qty: float = 0.0
    stop_loss: float | None = None
    take_profit: float | None = None


def size_position(equity: float, price: float, max_position_pct: float) -> int:
    """Whole-share quantity for a new position capped at ``max_position_pct``."""
    if price <= 0:
        return 0
    budget = equity * max_position_pct
    return int(budget // price)


def compute_bracket(
    price: float, side: str, stop_loss_pct: float, take_profit_pct: float
) -> tuple[float | None, float | None]:
    """Stop/target prices for a bracket order (long side)."""
    if side.lower() != "buy":
        return None, None  # exits are plain orders
    stop = round(price * (1 - stop_loss_pct), 2) if stop_loss_pct else None
    target = round(price * (1 + take_profit_pct), 2) if take_profit_pct else None
    return stop, target


def validate_order(
    account: dict[str, Any],
    positions: list[dict[str, Any]],
    symbol: str,
    side: str,
    qty: float,
    price: float,
) -> RiskDecision:
    """Gate a proposed order against current risk limits."""
    cfg = runtime_settings.get_all()
    equity = float(account.get("equity", 0)) or 1.0
    side = side.lower()

    if qty <= 0:
        return RiskDecision(ok=False, reason="quantity must be positive")
    if price <= 0:
        return RiskDecision(ok=False, reason="invalid price")

    if side == "sell":
        # Only allow selling what we hold (no shorting in the simulator).
        held = next((p for p in positions if p["symbol"] == symbol), None)
        if not held or held["qty"] < qty:
            return RiskDecision(
                ok=False, reason=f"cannot sell {qty} {symbol}: insufficient position"
            )
        return RiskDecision(ok=True, qty=qty)

    # ── BUY-side checks ────────────────────────────────────────────────
    order_value = qty * price
    if order_value > float(account.get("buying_power", 0)):
        return RiskDecision(ok=False, reason="insufficient buying power")

    # Per-position cap (existing exposure to this symbol + this order).
    existing = next((p for p in positions if p["symbol"] == symbol), None)
    existing_val = float(existing["market_value"]) if existing else 0.0
    pos_pct = (existing_val + order_value) / equity
    if pos_pct > cfg["max_position_pct"] + 1e-9:
        return RiskDecision(
            ok=False,
            reason=(
                f"position would be {pos_pct:.0%} of equity "
                f"(max {cfg['max_position_pct']:.0%})"
            ),
        )

    # Total exposure cap across all positions.
    invested = sum(float(p["market_value"]) for p in positions)
    total_pct = (invested + order_value) / equity
    if total_pct > cfg["max_total_exposure_pct"] + 1e-9:
        return RiskDecision(
            ok=False,
            reason=(
                f"total exposure would be {total_pct:.0%} "
                f"(max {cfg['max_total_exposure_pct']:.0%})"
            ),
        )

    stop, target = compute_bracket(
        price, side, cfg["stop_loss_pct"], cfg["take_profit_pct"]
    )
    return RiskDecision(ok=True, qty=qty, stop_loss=stop, take_profit=target)
