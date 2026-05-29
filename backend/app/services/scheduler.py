"""Background scheduler: periodic recommendation refresh + position monitoring.

During market hours it regenerates recommendations every few minutes and, when
``auto_trade`` is enabled, acts on them. Auto-trading can only ever place *paper*
orders: live orders require an explicit per-order human confirmation that the
scheduler cannot provide (see ``portfolio._live_gate``), so automation is
fail-safe by construction.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler

from .. import alpaca_client as ac
from ..config import settings
from . import portfolio, recommender, runtime_settings

log = logging.getLogger("scheduler")

_scheduler: BackgroundScheduler | None = None

# Latest cycle output, served to clients without recomputing.
LATEST: dict[str, Any] = {"recommendations": [], "generated_at": None, "auto_actions": []}

REFRESH_MINUTES = 15


def _market_open() -> bool:
    try:
        return ac.get_clock()["is_open"]
    except Exception:  # noqa: BLE001
        return False


def run_cycle(force: bool = False) -> dict[str, Any]:
    """One full pass: refresh recommendations and optionally auto-trade."""
    if not settings.has_credentials:
        return {"skipped": "no credentials"}
    if not force and not _market_open():
        return {"skipped": "market closed"}

    reco = recommender.generate(persist=True)
    actions: list[dict[str, Any]] = []

    if runtime_settings.get("auto_trade") and reco.get("configured"):
        actions = _auto_trade(reco)

    LATEST.update(
        recommendations=reco.get("recommendations", []),
        top_buys=reco.get("top_buys", []),
        top_sells=reco.get("top_sells", []),
        generated_at=reco.get("generated_at"),
        auto_actions=actions,
    )
    return {"recommendations": len(reco.get("recommendations", [])), "auto_actions": actions}


def _auto_trade(reco: dict[str, Any]) -> list[dict[str, Any]]:
    """Buy top-ranked BUYs we don't hold; sell holdings that flipped to SELL."""
    actions: list[dict[str, Any]] = []
    snap = portfolio.snapshot()
    if not snap["configured"]:
        return actions
    held = {p["symbol"] for p in snap["positions"]}

    # Exits: any held symbol now rated SELL.
    sell_syms = {d["symbol"] for d in reco.get("recommendations", []) if d["action"] == "SELL"}
    for p in snap["positions"]:
        if p["symbol"] in sell_syms and p["qty"] > 0:
            actions.append(_try(p["symbol"], "sell", p["qty"]))

    # Entries: top BUYs we don't already hold (risk caps decide how many fill).
    for d in reco.get("top_buys", []):
        if d["symbol"] not in held:
            actions.append(_try(d["symbol"], "buy", None))

    return actions


def _try(symbol: str, side: str, qty: float | None) -> dict[str, Any]:
    try:
        res = portfolio.place_order(symbol, side, qty=qty, source="auto")
        return {"symbol": symbol, "side": side, "status": "submitted", "detail": res["order"]}
    except portfolio.OrderRejected as e:
        return {"symbol": symbol, "side": side, "status": "rejected", "reason": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"symbol": symbol, "side": side, "status": "error", "reason": str(e)}


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None or not settings.has_credentials:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        run_cycle,
        "interval",
        minutes=REFRESH_MINUTES,
        id="signal_cycle",
        next_run_time=dt.datetime.now(dt.timezone.utc),  # run once at startup
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    log.info("Scheduler started (refresh every %d min).", REFRESH_MINUTES)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
