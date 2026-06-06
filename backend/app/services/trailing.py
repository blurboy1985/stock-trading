"""Live trailing-stop ratchet for held positions (paper).

The backtester already trails ATR stops (see ``backtest/engine.py``); this brings
the same behaviour to live paper positions. Each scheduler cycle we sample every
holding's price, advance its high-water mark, and ratchet the bracket's *stop*
leg up toward ``high_water - k*ATR``. The stop only ever tightens — it never
loosens and is never moved above the live price — so the existing take-profit leg
of the OCO bracket is left untouched (we amend in place via
``broker_client.replace_order``, when supported by the selected broker).

It is intentionally conservative:
* Only positions that already have an open bracket stop leg are touched — we
  ratchet an existing stop, we never create one.
* ``trailing_stop_dry_run`` (default on) logs the intended move without calling
  the broker, so you can watch it behave before letting it amend real orders.
* The broker is the source of truth for the position; :class:`PositionTrail` only
  remembers the high-water mark between cycles, and is reset when a position is
  re-opened or averaged (entry price moves).
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from sqlalchemy import select

from .. import broker_client as ac
from ..config import settings
from ..db import SessionLocal
from ..models import PositionTrail
from ..strategies.volatility import atr as _atr_series
from . import runtime_settings

log = logging.getLogger("trailing")

_ATR_PERIOD = 14
# Don't churn the broker for sub-cent ratchets; require a meaningful move.
_MIN_STEP = 0.01


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _atr_dollars(symbol: str) -> float | None:
    """ATR in price terms from recent daily bars, or ``None`` if unavailable."""
    start = dt.date.today() - dt.timedelta(days=60)
    try:
        df = ac.get_bars(symbol, start)
    except Exception:  # noqa: BLE001 — bars are best-effort; skip this symbol
        return None
    if df is None or len(df) < _ATR_PERIOD + 2:
        return None
    try:
        val = float(_atr_series(df["high"], df["low"], df["close"], _ATR_PERIOD).iloc[-1])
    except Exception:  # noqa: BLE001
        return None
    return val if val > 0 else None


def _open_stop_legs() -> dict[str, dict[str, Any]]:
    """Map ``symbol -> open stop-sell order`` (the bracket's stop leg).

    Best-effort: an orders outage just means nothing is ratcheted this cycle.
    """
    try:
        orders = ac.list_orders(status="open", limit=500)
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, dict[str, Any]] = {}
    for o in orders:
        if o.get("side") != "sell" or not o.get("stop_price"):
            continue
        cur = out.get(o["symbol"])
        # If a symbol somehow has two stop legs, keep the higher one.
        if cur is None or (o["stop_price"] or 0) > (cur["stop_price"] or 0):
            out[o["symbol"]] = o
    return out


def _evaluate(
    db: Any, pos: dict[str, Any], cfg: dict[str, Any],
    stop_legs: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Advance one position's trail and ratchet its stop. Returns the move, if any."""
    symbol = pos["symbol"]
    qty = float(pos.get("qty") or 0)
    side = pos.get("side") or "long"
    price = float(pos.get("current_price") or 0)
    entry = float(pos.get("avg_entry_price") or 0)
    if qty <= 0 or side != "long" or price <= 0:
        return None

    # Load (or seed/reset) the high-water mark. A moved entry price means the
    # position was re-opened or averaged, so start the trail over.
    row = db.get(PositionTrail, symbol)
    if row is None:
        row = PositionTrail(symbol=symbol, entry_price=entry, high_water=max(entry, price))
        db.add(row)
    elif abs(row.entry_price - entry) > _MIN_STEP:
        row.entry_price = entry
        row.high_water = max(entry, price)
        row.last_stop = None
    if price > row.high_water:
        row.high_water = price
    row.updated_at = _utcnow()

    # We only ratchet an *existing* bracket stop leg; never create one.
    stop_order = stop_legs.get(symbol)
    if stop_order is None:
        return None
    current_stop = float(stop_order.get("stop_price") or 0)

    atr_d = _atr_dollars(symbol)
    if not atr_d:
        return None
    trail = round(row.high_water - float(cfg["trailing_atr_mult"]) * atr_d, 2)
    if trail <= current_stop + _MIN_STEP:
        return None  # would loosen or barely move — leave it

    # Keep the stop safely below the live price so it can't trigger on submit.
    ceiling = round(price - max(_MIN_STEP, round(price * 0.001, 2)), 2)
    new_stop = min(trail, ceiling)
    if new_stop <= current_stop + _MIN_STEP:
        return None

    move = {
        "symbol": symbol,
        "order_id": stop_order["id"],
        "from": current_stop,
        "to": new_stop,
        "high_water": round(row.high_water, 2),
        "atr": round(atr_d, 4),
    }
    if cfg.get("trailing_stop_dry_run", True):
        move["dry_run"] = True
        log.info(
            "trailing[dry-run] %s stop %.2f -> %.2f (hw %.2f, atr %.3f)",
            symbol, current_stop, new_stop, row.high_water, atr_d,
        )
        return move

    ac.replace_order(stop_order["id"], stop_price=new_stop)
    row.last_stop = new_stop
    log.info("trailing %s stop %.2f -> %.2f (hw %.2f)", symbol, current_stop, new_stop, row.high_water)
    return move


def _prune(db: Any, held: set[str]) -> None:
    """Drop trail rows for symbols we no longer hold (position fully closed)."""
    for row in db.scalars(select(PositionTrail)).all():
        if row.symbol not in held:
            db.delete(row)


def run(force: bool = False) -> dict[str, Any]:
    """Ratchet trailing stops across all held positions. Never raises.

    ``force`` is accepted for symmetry with the scheduler but isn't needed —
    the caller already gates on market hours.
    """
    cfg = runtime_settings.get_all()
    if not cfg.get("trailing_stop_enabled"):
        return {"skipped": "disabled"}
    if not settings.has_credentials:
        return {"skipped": "no credentials"}

    try:
        positions = ac.get_positions()
    except Exception as e:  # noqa: BLE001 — a positions outage skips the pass
        log.warning("trailing: could not fetch positions: %s", e)
        return {"error": str(e)}

    stop_legs = _open_stop_legs()
    moves: list[dict[str, Any]] = []
    with SessionLocal() as db:
        held: set[str] = set()
        for pos in positions:
            held.add(pos["symbol"])
            try:
                m = _evaluate(db, pos, cfg, stop_legs)
            except Exception:  # noqa: BLE001 — one bad symbol must not abort the pass
                log.exception("trailing: failed on %s", pos.get("symbol"))
                m = None
            if m:
                moves.append(m)
        _prune(db, held)
        db.commit()

    return {"moves": moves, "dry_run": bool(cfg.get("trailing_stop_dry_run", True))}
