"""Pre-trade risk checks and position sizing.

Every order — manual, auto, paper, or live — must pass ``validate_order`` before
reaching the broker. This is the single chokepoint enforcing position-size caps,
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


# Floor on ATR% so a near-zero vol reading can't blow up the target-vol weight.
_ATR_FLOOR = 0.005


def target_weight(
    atr_pct: float | None,
    conviction: float,
    *,
    target_risk_pct: float,
    max_position_pct: float,
) -> float:
    """Volatility-targeted, conviction-scaled portfolio weight for a long.

    Lower-volatility names earn a larger weight (up to ``max_position_pct``) so
    each position contributes a comparable amount of risk; the weight is then
    scaled by conviction (with a floor so a valid BUY is never dust).
    """
    if atr_pct and atr_pct > 0:
        raw = target_risk_pct / max(atr_pct, _ATR_FLOOR)
    else:
        raw = max_position_pct  # unknown vol -> fall back to the cap
    weight = min(raw, max_position_pct)
    conv_factor = 0.4 + 0.6 * max(0.0, min(1.0, conviction))
    return weight * conv_factor


def size_position_vol_target(
    equity: float,
    price: float,
    atr_pct: float | None,
    conviction: float,
    *,
    target_risk_pct: float,
    max_position_pct: float,
) -> int:
    """Whole-share quantity from :func:`target_weight` (caps still apply later)."""
    if price <= 0:
        return 0
    weight = target_weight(
        atr_pct, conviction,
        target_risk_pct=target_risk_pct, max_position_pct=max_position_pct,
    )
    return int((equity * weight) // price)


def compute_bracket(
    price: float,
    side: str,
    stop_loss_pct: float,
    take_profit_pct: float,
    atr: float | None = None,
    atr_stop_mult: float = 0.0,
) -> tuple[float | None, float | None]:
    """Stop/target prices for a bracket order (long side).

    When ``atr_stop_mult`` > 0 and an ``atr`` (in price terms) is supplied, the
    stop is placed ``atr_stop_mult`` ATRs below the fill — a volatility-scaled
    stop that adapts to each name — overriding the flat ``stop_loss_pct``.
    """
    if side.lower() != "buy":
        return None, None  # exits are plain orders
    if atr_stop_mult and atr and atr > 0:
        stop = round(price - atr_stop_mult * atr, 2)
    elif stop_loss_pct:
        stop = round(price * (1 - stop_loss_pct), 2)
    else:
        stop = None
    target = round(price * (1 + take_profit_pct), 2) if take_profit_pct else None
    return stop, target


def validate_order(
    account: dict[str, Any],
    positions: list[dict[str, Any]],
    symbol: str,
    side: str,
    qty: float,
    price: float,
    atr: float | None = None,
) -> RiskDecision:
    """Gate a proposed order against current risk limits.

    ``atr`` (in price terms), when supplied alongside a configured
    ``atr_stop_mult``, yields a volatility-scaled stop instead of the flat %.
    """
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

    # Sector concentration cap: per-position vol sizing controls single-name
    # risk but says nothing about buying six 0.9-correlated names in one sector.
    # Best-effort — skipped when the candidate's sector can't be resolved from
    # the (cache-only) lookup, so it never blocks on missing data.
    sector_cap = cfg.get("max_sector_exposure_pct", 0.0)
    if sector_cap:
        from ..strategies.fundamentals import cached_sector

        sector = cached_sector(symbol)
        if sector:
            same_sector = sum(
                float(p["market_value"])
                for p in positions
                if cached_sector(p["symbol"]) == sector
            )
            sector_pct = (same_sector + order_value) / equity
            if sector_pct > sector_cap + 1e-9:
                return RiskDecision(
                    ok=False,
                    reason=(
                        f"{sector} exposure would be {sector_pct:.0%} "
                        f"(max {sector_cap:.0%})"
                    ),
                )

    stop, target = compute_bracket(
        price, side, cfg["stop_loss_pct"], cfg["take_profit_pct"],
        atr=atr, atr_stop_mult=cfg.get("atr_stop_mult", 0.0),
    )
    return RiskDecision(ok=True, qty=qty, stop_loss=stop, take_profit=target)
