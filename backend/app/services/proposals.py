"""Auto-trade proposals: propose → confirm → execute, with a full audit trail.

When ``auto_trade`` is enabled the scheduler creates auditable proposal rows each
cycle and immediately executes confirmable ones through the same paper-only order
path. Manual confirm/reject endpoints still exist for review workflows and for
any proposal left pending by an execution/risk issue. Live orders remain blocked
by ``portfolio.place_order`` / ``portfolio._live_gate`` unless live mode is
explicitly enabled elsewhere.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select

from .. import broker_client as ac
from ..config import settings
from ..db import SessionLocal
from ..models import Recommendation, TradeProposal
from . import portfolio, risk, runtime_settings


class ProposalError(Exception):
    """A proposal cannot be acted on (already decided, blocked, or rejected)."""


class ProposalNotFound(ProposalError):
    """No proposal with the given id."""


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# ── Building proposals from a recommendation cycle ────────────────────────────


def build_from_reco(reco: dict[str, Any]) -> list[dict[str, Any]]:
    """Create auditable entry/exit rows for the latest recommendations.

    Mirrors the old auto-trader's selection logic: buy top-ranked BUYs we don't
    hold, sell holdings that flipped to SELL. The scheduler normally follows this
    with :func:`confirm_all` so eligible rows are auto-executed; standalone callers
    can still review/confirm manually.
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

        # Work against a virtual copy of positions while building a batch. A
        # single cycle can propose several buys before any of them fills, so
        # sizing each candidate against only the starting portfolio creates
        # doomed rows that later fail the same risk checks during confirmation.
        planned_positions = [dict(p) for p in positions]

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
                      account, planned_positions, equity, regime)
            )

        # Benchmark core / cash sweep: keep idle capital invested in a broad ETF
        # (usually RSP) before the active stock overlay. This is buy-only here:
        # we do not tactically exit the core just because no active signal fires.
        core = _core_buy_candidate(cfg, account, positions, equity, reco_by_sym, regime)
        if core is not None:
            sym, qty, price, d = core
            if (sym, "buy") not in pending and (sym, "buy") not in open_orders:
                qty = _cap_buy_qty_for_risk(account, planned_positions, sym, qty, price, cfg)
                if qty > 0:
                    created.append(
                        _make(
                            db, "buy", sym, qty, price, d, cfg,
                            account, planned_positions, equity, regime,
                        )
                    )
                    _apply_virtual_buy(planned_positions, sym, qty, price)

        # Entries: top BUYs we don't already hold.
        core_symbol = str(cfg.get("core_symbol") or "").upper() if cfg.get("core_target_pct") else ""
        for d in reco.get("top_buys", []):
            sym = d["symbol"]
            if core_symbol and sym == core_symbol:
                continue
            if sym in held or (sym, "buy") in pending or (sym, "buy") in open_orders:
                continue
            price = float(d.get("price") or 0.0)
            if price <= 0:
                continue
            qty = _entry_qty(d, cfg, equity, price)
            qty = _cap_buy_qty_for_risk(account, planned_positions, sym, qty, price, cfg)
            if qty <= 0:
                continue
            created.append(
                _make(db, "buy", sym, qty, price, d, cfg,
                      account, planned_positions, equity, regime)
            )
            _apply_virtual_buy(planned_positions, sym, qty, price)

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


def _cap_buy_qty_for_risk(
    account: dict[str, Any],
    positions: list[dict[str, Any]],
    symbol: str,
    qty: float,
    price: float,
    cfg: dict[str, Any],
) -> int:
    """Reduce a BUY quantity so the proposal is actually confirmable.

    Recommendation sizing is intentionally signal-driven, but confirmation goes
    through hard portfolio risk gates. This helper keeps the audit trail clean by
    clipping proposed quantities to the remaining per-symbol, total-exposure, and
    buying-power budgets, including buys already planned in this same cycle.
    """
    if qty <= 0 or price <= 0:
        return 0
    equity = float(account.get("equity") or 0.0)
    if equity <= 0:
        return 0

    buying_power_budget = max(0.0, float(account.get("buying_power") or 0.0))
    invested = sum(float(p.get("market_value") or 0.0) for p in positions)
    total_budget = max(0.0, equity * float(cfg["max_total_exposure_pct"]) - invested)

    existing = next(
        (p for p in positions if str(p.get("symbol", "")).upper() == symbol.upper()),
        None,
    )
    existing_val = float(existing.get("market_value") or 0.0) if existing else 0.0
    position_limit = float(cfg["max_position_pct"])
    core_symbol = str(cfg.get("core_symbol") or "").upper()
    core_target = float(cfg.get("core_target_pct") or 0.0)
    if core_target > 0 and symbol.upper() == core_symbol:
        position_limit = max(
            position_limit,
            core_target + float(cfg.get("core_rebalance_threshold_pct") or 0.0),
        )
    position_budget = max(0.0, equity * position_limit - existing_val)

    budget = min(float(qty) * price, buying_power_budget, total_budget, position_budget)
    if budget <= 0:
        return 0
    return int(budget // price)


def _apply_virtual_buy(
    positions: list[dict[str, Any]], symbol: str, qty: float, price: float
) -> None:
    """Reflect an in-cycle planned buy in the virtual positions list."""
    sym = symbol.upper()
    value = float(qty) * float(price)
    existing = next(
        (p for p in positions if str(p.get("symbol", "")).upper() == sym),
        None,
    )
    if existing is None:
        positions.append({"symbol": sym, "qty": float(qty), "market_value": value})
        return
    existing["qty"] = float(existing.get("qty") or 0.0) + float(qty)
    existing["market_value"] = float(existing.get("market_value") or 0.0) + value


def _core_buy_candidate(
    cfg: dict[str, Any],
    account: dict[str, Any],
    positions: list[dict[str, Any]],
    equity: float,
    reco_by_sym: dict[str, dict[str, Any]],
    regime: str | None,
) -> tuple[str, int, float, dict[str, Any]] | None:
    """Return a buy proposal that sweeps idle cash into the benchmark core."""
    target_pct = float(cfg.get("core_target_pct") or 0.0)
    if target_pct <= 0 or equity <= 0:
        return None
    if regime and regime.lower() in {"risk_off", "bear"}:
        return None
    sym = str(cfg.get("core_symbol") or "RSP").upper()
    threshold = float(cfg.get("core_rebalance_threshold_pct") or 0.02)
    held = next((p for p in positions if p["symbol"] == sym), None)
    current_value = float(held.get("market_value") or 0.0) if held else 0.0
    target_value = equity * min(1.0, max(0.0, target_pct))
    gap = target_value - current_value
    if gap / equity < threshold:
        return None
    price = float((reco_by_sym.get(sym) or {}).get("price") or 0.0)
    if price <= 0:
        try:
            price = float(ac.get_latest_quote(sym).get("mid") or 0.0)
        except Exception:  # noqa: BLE001 — no quote, no core proposal this cycle
            price = 0.0
    if price <= 0:
        return None
    budget = min(gap, float(account.get("buying_power") or 0.0))
    qty = int(budget // price)
    if qty <= 0:
        return None
    d = dict(reco_by_sym.get(sym) or {})
    d.update(
        {
            "symbol": sym,
            "action": "BUY",
            "price": price,
            "conviction": d.get("conviction", 1.0),
            "atr_pct": d.get("atr_pct"),
            "reasons": [
                f"benchmark core cash sweep toward {target_pct:.0%} target",
                "keeps idle cash invested while active stock signals run as overlay",
            ],
            "breakdown": d.get("breakdown") or {
                "core": {
                    "score": 1.0,
                    "weight": 1.0,
                    "reasons": ["benchmark core allocation"],
                    "metrics": {"target_pct": target_pct, "current_pct": current_value / equity},
                }
            },
        }
    )
    return sym, qty, price, d


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
    breakdown = d.get("breakdown") or {}

    # Dry-run the same risk gate confirm/place_order will enforce, so the user
    # sees up front whether (and why) a trade can't go through. Pass ATR (in
    # price terms) so a configured ATR stop is volatility-scaled per name.
    atr_dollars = (atr_pct * price) if (atr_pct and price) else None
    decision = risk.validate_order(
        account, positions, symbol, side, qty, price, atr=atr_dollars
    )
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
        breakdown_json=breakdown,
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
        return [_serialize(r, db) for r in db.scalars(q.limit(200)).all()]


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
        if row.side == "sell":
            # Exit via close_position, which cancels the entry's open bracket
            # (OCO stop/target) legs first. A plain market sell would leave those
            # legs working — one could later fire a second sell and open a short
            # at the broker, which validate_order can't prevent (the leg lives at
            # broker). Proposals always exit the full held qty, so a full close
            # is equivalent.
            res = portfolio.close_position(row.symbol, source="auto")
        else:
            res = portfolio.place_order(row.symbol, row.side, qty=row.qty, source="auto")
    except Exception as e:  # noqa: BLE001 — capture every failure on the row
        row.status = "failed"
        row.result = str(e)
        row.decided_at = _utcnow()
        return {"ok": False, "error": str(e)}
    order = res.get("order") or {}
    row.status = "executed"
    row.result = order.get("broker_order_id") or order.get("alpaca_order_id") or order.get("id") or "submitted"
    row.decided_at = _utcnow()
    return {"ok": True, "order": order}


def _serialize(r: TradeProposal, db: Any | None = None) -> dict[str, Any]:
    breakdown = r.breakdown_json or {}
    if not breakdown and db is not None:
        # Backfill older proposal history from the persisted recommendation row.
        # New proposals store breakdown_json directly, but existing history was
        # created before that column existed. Prefer the recommendation snapshot
        # closest to, but not after, the proposal creation time.
        reco = db.scalars(
            select(Recommendation)
            .where(Recommendation.symbol == r.symbol)
            .where(Recommendation.created_at <= r.created_at)
            .order_by(Recommendation.created_at.desc())
            .limit(1)
        ).first()
        breakdown = reco.breakdown if reco and reco.breakdown else {}
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
        "breakdown": breakdown,
        "regime": r.regime,
        "blocked_reason": r.blocked_reason,
        "status": r.status,
        "result": r.result,
        "source": r.source,
        "is_paper": r.is_paper,
    }
