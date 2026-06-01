"""Background scheduler: periodic recommendation refresh + auto-trade proposals.

During market hours it regenerates recommendations every few minutes and, when
``auto_trade`` is enabled, *proposes* entries/exits (it never places orders
itself). The user confirms each proposal in the UI, and only that explicit
confirm reaches the broker — always paper (see ``portfolio._live_gate``), so
automation is fail-safe by construction.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler

from .. import broker_client as ac
from ..config import settings
from . import proposals, recommender, runtime_settings, trailing

log = logging.getLogger("scheduler")

_scheduler: BackgroundScheduler | None = None

# Latest cycle output, served to clients without recomputing.
LATEST: dict[str, Any] = {
    "recommendations": [], "generated_at": None, "regime": None,
}

REFRESH_MINUTES = 15


def _market_open() -> bool:
    try:
        return ac.get_clock()["is_open"]
    except Exception:  # noqa: BLE001
        return False


def run_cycle(force: bool = False) -> dict[str, Any]:
    """One full pass: refresh recommendations and (if on) propose auto-trades."""
    if not settings.has_credentials:
        return {"skipped": "no credentials"}
    if not force and not _market_open():
        return {"skipped": "market closed"}

    reco = recommender.generate(persist=True)
    proposed: list[dict[str, Any]] = []

    if runtime_settings.get("auto_trade") and reco.get("configured"):
        # Supersede last cycle's untouched proposals, then propose fresh ones.
        proposals.expire_stale()
        proposed = proposals.build_from_reco(reco)

    # Ratchet trailing stops on held positions (no-op unless enabled). Self-gated
    # and never raises, but wrap defensively so it can't break the cycle.
    trail: dict[str, Any] = {}
    if runtime_settings.get("trailing_stop_enabled"):
        try:
            trail = trailing.run()
        except Exception:  # noqa: BLE001
            log.exception("trailing-stop pass failed")
            trail = {"error": "exception"}

    LATEST.update(
        recommendations=reco.get("recommendations", []),
        top_buys=reco.get("top_buys", []),
        top_sells=reco.get("top_sells", []),
        generated_at=reco.get("generated_at"),
        regime=reco.get("regime"),
    )
    return {
        "recommendations": len(reco.get("recommendations", [])),
        "proposals": len(proposed),
        "trailing_moves": len(trail.get("moves", [])),
    }


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
