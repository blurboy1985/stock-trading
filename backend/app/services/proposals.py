"""Auto-trade proposals: propose → confirm → execute, with a full audit trail.

When ``auto_trade`` is enabled the scheduler *proposes* trades each cycle instead
of placing them. Each proposal records what we'd do, the sized quantity, an
estimated cost, and a human-readable rationale, plus a dry-run risk check. The
user confirms or rejects; only an explicit confirm reaches the broker (always
paper — see ``portfolio.place_order`` / ``portfolio._live_gate``).
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select

from .. import alpaca_client as ac
from ..config import settings
from ..db import SessionLocal
from ..models import TradeProposal
from . import portfolio, risk, runtime_settings


class ProposalError(Exception):
    """A proposal cannot be acted on (already decided, blocked, or rejected)."""


class ProposalNotFound(ProposalError):
    """No proposal with the given id."""


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# ── Building proposals from a recommendation cycle ────────────────────────────


def build_from_reco(reco: dict[str, Any]) -> list[dict[str, Any]]:
    """Propose (don't place) entries/exits for the latest recommendations.

    Mirrors the old auto-trader's selection logic: buy top-ranked BUYs we don't
    hold, sell holdings that flipped to SELL — but persists each as a *pending*
    proposal awaiting human confirmation.
    """
    snap = portfolio.snapshot()
    if not snap["configured"]:
        return []
    account = snap["account"]
    positions = snap["positions"]
    equity = float(account.get("equity") or 0.0)
    cfg = runtime_settings.get_all()
    held = {p["symbol"]: p for p in positions}
    regime = (reco.get("regime") or {}).get("label")
    reco_by_sym = {d["symbol"]: d for d in reco.get("recommendations", [])}

    # Symbols with an open (unfilled) order at the broker — e.g. a confirmed buy
    # that hasn't filled yet (queued outside market hours, or still working).
    # Once a proposal is executed it's no longer "pending", and the position
    # won't appear in `held` until the order fills, so without this guard the
    # same buy/sell gets re-proposed every cycle. Best-effort: an orders outage
    # must not block proposing fresh trades.
    try:
        open_orders = {(o["symbol"], o["side"]) for o in ac.list_orders(status="open", limit=500)}
    except Exception:  # noqa: BLE001 — open-order lookup is advisory only
        open_orders = set()

    created: list[TradeProposal] = []
    with SessionLocal() as db:
        pending = {
            (r.symbol, r.side)
            for r in db.scalars(
                select(TradeProposal).where(TradeProposal.status == "pending")
            ).all()
        }

        # Exits: any held symbol now rated SELL.
        sell_syms = {d["symbol"] for d in reco.get("recommendations", []) if d["action"] == "SELL"}
        for sym, p in held.items():
            if sym not in sell_syms or float(p["qty"]) <= 0:
                continue
            if (sym, "sell") in pending or (sym, "sell") in open_orders:
                continue
            d = reco_by_sym.get(sym, {})
            price = float(p.get("current_price") or d.get("price") or 0.0)
            if price <= 0:
                continue
            created.append(
                _make(db, "sell", sym, float(p["qty"]), price, d, cfg,
                      account, positions, equity, regime)
            )

        # Entries: top BUYs we don't already hold.
        for d in reco.get("top_buys", []):
            sym = d["symbol"]
            if sym in held or (sym, "buy") in pending or (sym, "buy") in open_orders:
                continue
            price = float(d.get("price") or 0.0)
            if price <= 0:
                continue
            qty = _entry_qty(d, cfg, equity, price)
            if qty <= 0:
                continue
            created.append(
                _make(db, "buy", sym, qty, price, d, cfg,
                      account, positions, equity, regime)
            )

        db.commit()
        return [_serialize(r) for r in created]


def _entry_qty(d: dict[str, Any], cfg: dict[str, Any], equity: float, price: float) -> float:
    """Sized entry quantity, honoring the user's vol-sizing preference.

    Prefers the recommendation's already-computed ``suggested_qty`` (which the
    Recommendations view shows), falling back to the same sizing helpers.
    """
    sug = d.get("suggested_qty")
    if sug and float(sug) > 0:
        return float(sug)
    conviction = d.get("conviction", abs(d.get("score", 0.0)))
    if cfg["use_vol_sizing"]:
        return float(
            risk.size_position_vol_target(
                equity, price, d.get("atr_pct"), conviction,
                target_risk_pct=cfg["target_risk_pct"],
                max_position_pct=cfg["max_position_pct"],
            )
        )
    return float(risk.size_position(equity, price, cfg["max_position_pct"]))


def _make(
    db: Any, side: str, symbol: str, qty: float, price: float,
    d: dict[str, Any], cfg: dict[str, Any], account: dict[str, Any],
    positions: list[dict[str, Any]], equity: float, regime: str | None,
) -> TradeProposal:
    est_cost = qty * price
    equity_pct = (est_cost / equity) if equity else None
    conviction = d.get("conviction")
    atr_pct = d.get("atr_pct")
    reasons = d.get("reasons") or []

    # Dry-run the same risk gate confirm/place_order will enforce, so the user
    # sees up front whether (and why) a trade can't go through.
    decision = risk.validate_order(account, positions, symbol, side, qty, price)
    blocked = None if decision.ok else decision.reason

    row = TradeProposal(
        symbol=symbol,
        side=side,
        qty=qty,
        price=price,
        est_cost=est_cost,
        equity_pct=equity_pct,
        conviction=conviction,
        atr_pct=atr_pct,
        rationale=_explain(side, symbol, qty, est_cost, equity_pct, conviction, atr_pct, reasons, cfg, regime),
        reasons_json=list(reasons),
        regime=regime,
        blocked_reason=blocked,
        status="pending",
        source="auto",
        is_paper=settings.is_paper,
    )
    db.add(row)
    return row


def _explain(
    side: str, symbol: str, qty: float, est_cost: float, equity_pct: float | None,
    conviction: float | None, atr_pct: float | None, reasons: list[str],
    cfg: dict[str, Any], regime: str | None,
) -> str:
    qty_s = f"{int(qty)}" if float(qty).is_integer() else f"{qty:.2f}"
    cost = f"~${est_cost:,.0f}"
    sig = " · ".join(reasons[:4]) if reasons else "ranked by risk-adjusted score"
    reg = f" Regime: {regime}." if regime else ""
    if side == "sell":
        return (
            f"SELL {qty_s} {symbol} ({cost}) — rating flipped to SELL; exiting "
            f"the position.{reg} Signals: {sig}."
        )
    pct = f", {equity_pct * 100:.1f}% of equity" if equity_pct else ""
    if cfg.get("use_vol_sizing"):
        if conviction is not None and atr_pct:
            size = f"Vol-target sizing: conviction {conviction:.2f}, ATR {atr_pct * 100:.1f}%."
        else:
            size = "Vol-target sizing (conviction-scaled, volatility-adjusted)."
    else:
        size = f"Fixed sizing capped at {cfg['max_position_pct'] * 100:.0f}% of equity."
    return f"BUY {qty_s} {symbol} ({cost}{pct}). {size}{reg} Signals: {sig}."


# ── Reading + acting on proposals ─────────────────────────────────────────────


def list_proposals(status: str | None = None) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        q = select(TradeProposal).order_by(TradeProposal.created_at.desc())
        if status:
            q = q.where(TradeProposal.status == status)
        return [_serialize(r) for r in db.scalars(q.limit(200)).all()]


def confirm(proposal_id: int) -> dict[str, Any]:
    """Execute a single pending proposal. Raises on a bad/blocked/failed order."""
    with SessionLocal() as db:
        row = _load_pending(db, proposal_id)
        if row.blocked_reason:
            raise ProposalError(f"cannot confirm: {row.blocked_reason}")
        out = _execute(db, row)
        db.commit()
        if out["ok"]:
            return {"proposal": _serialize(row), "order": out["order"]}
        raise ProposalError(out["error"])


def confirm_all() -> dict[str, Any]:
    """Execute every confirmable (non-blocked) pending proposal; never raises."""
    results: list[dict[str, Any]] = []
    with SessionLocal() as db:
        rows = db.scalars(
            select(TradeProposal).where(TradeProposal.status == "pending")
        ).all()
        for row in rows:
            if row.blocked_reason:
                continue
            out = _execute(db, row)
            results.append(
                {"proposal_id": row.id, "symbol": row.symbol, "side": row.side, **out}
            )
        db.commit()
    return {"results": results}


def reject(proposal_id: int) -> dict[str, Any]:
    with SessionLocal() as db:
        row = _load_pending(db, proposal_id)
        row.status = "rejected"
        row.decided_at = _utcnow()
        db.commit()
        return {"proposal": _serialize(row)}


def expire_stale(max_age_minutes: int | None = None) -> int:
    """Expire pending proposals older than the refresh window (kept fresh per cycle)."""
    from .scheduler import REFRESH_MINUTES  # local import: avoid circular import

    cutoff = _utcnow() - dt.timedelta(minutes=max_age_minutes or REFRESH_MINUTES)
    with SessionLocal() as db:
        rows = db.scalars(
            select(TradeProposal).where(
                TradeProposal.status == "pending",
                TradeProposal.created_at < cutoff,
            )
        ).all()
        for row in rows:
            row.status = "expired"
            row.decided_at = _utcnow()
        db.commit()
        return len(rows)


# ── helpers ───────────────────────────────────────────────────────────────────


def _load_pending(db: Any, proposal_id: int) -> TradeProposal:
    row = db.get(TradeProposal, proposal_id)
    if row is None:
        raise ProposalNotFound("proposal not found")
    if row.status != "pending":
        raise ProposalError(f"proposal already {row.status}")
    return row


def _execute(db: Any, row: TradeProposal) -> dict[str, Any]:
    """Place a pending row's order, mutating its status. Does not raise."""
    try:
        res = portfolio.place_order(row.symbol, row.side, qty=row.qty, source="auto")
    except Exception as e:  # noqa: BLE001 — capture every failure on the row
        row.status = "failed"
        row.result = str(e)
        row.decided_at = _utcnow()
        return {"ok": False, "error": str(e)}
    order = res.get("order") or {}
    row.status = "executed"
    row.result = order.get("alpaca_order_id") or order.get("id") or "submitted"
    row.decided_at = _utcnow()
    return {"ok": True, "order": order}


def _serialize(r: TradeProposal) -> dict[str, Any]:
    return {
        "id": r.id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "decided_at": r.decided_at.isoformat() if r.decided_at else None,
        "symbol": r.symbol,
        "side": r.side,
        "qty": r.qty,
        "price": r.price,
        "est_cost": r.est_cost,
        "equity_pct": r.equity_pct,
        "conviction": r.conviction,
        "atr_pct": r.atr_pct,
        "rationale": r.rationale,
        "reasons": r.reasons_json or [],
        "regime": r.regime,
        "blocked_reason": r.blocked_reason,
        "status": r.status,
        "result": r.result,
        "source": r.source,
        "is_paper": r.is_paper,
    }
