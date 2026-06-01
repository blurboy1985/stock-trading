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
import threading
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler

from .. import broker_client as ac
from ..config import settings
from . import proposals, recommender, runtime_settings, trailing

log = logging.getLogger("scheduler")

_scheduler: BackgroundScheduler | None = None
_cycle_lock = threading.Lock()

# Latest cycle output, served to clients without recomputing.
LATEST: dict[str, Any] = {
    "recommendations": [],
    "generated_at": None,
    "regime": None,
    "top_buys": [],
    "top_sells": [],
    "message": None,
    "errors": {},
    "refresh_status": "idle",
}

REFRESH_MINUTES = 15


def _market_open() -> bool:
    try:
        return ac.get_clock()["is_open"]
    except Exception:  # noqa: BLE001
        return False


def run_cycle(force: bool = False) -> dict[str, Any]:
    """One full pass: refresh recommendations and (if on) propose auto-trades.

    The UI can request recommendations while the startup scheduler is already
    scanning. Avoid concurrent cycles: IBKR allows one session per client id and
    concurrent broker calls can wedge page loads.
    """
    if not _cycle_lock.acquire(blocking=False):
        LATEST["refresh_status"] = "running"
        return {"skipped": "cycle already running"}
    try:
        LATEST.update(refresh_status="running", message=None, errors={})
        if not settings.has_credentials:
            message = "IBKR is not configured. Set IBKR_HOST, IBKR_PORT and IBKR_CLIENT_ID, then restart the backend."
            LATEST.update(
                recommendations=[],
                top_buys=[],
                top_sells=[],
                generated_at=None,
                regime=None,
                message=message,
                errors={},
                refresh_status="skipped",
            )
            return {"skipped": "no credentials", "message": message}
        if not force and not _market_open():
            LATEST.update(refresh_status="skipped", message="Market is closed; using the last generated recommendations.")
            return {"skipped": "market closed", "message": LATEST.get("message")}

        reco = recommender.generate(persist=True)
        proposed: list[dict[str, Any]] = []
        proposal_error: str | None = None

        if runtime_settings.get("auto_trade") and reco.get("configured"):
            # Supersede last cycle's untouched proposals, then propose fresh ones.
            # Proposal building needs portfolio/account data; keep failures from
            # preventing the recommendations page from loading.
            try:
                proposals.expire_stale()
                proposed = proposals.build_from_reco(reco)
            except Exception as exc:  # noqa: BLE001
                log.exception("auto-proposal pass failed")
                proposal_error = f"{type(exc).__name__}: {exc}"

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
            proposal_error=proposal_error,
            message=reco.get("message"),
            errors=reco.get("errors", {}),
            refresh_status="complete",
        )
        return {
            "recommendations": len(reco.get("recommendations", [])),
            "proposals": len(proposed),
            "proposal_error": proposal_error,
            "trailing_moves": len(trail.get("moves", [])),
            "message": reco.get("message"),
        }
    except Exception as exc:  # noqa: BLE001
        message = f"Refresh failed: {type(exc).__name__}: {exc}"
        LATEST.update(message=message, refresh_status="failed")
        log.exception("recommendation refresh failed")
        return {"error": message}
    finally:
        if LATEST.get("refresh_status") == "running":
            LATEST["refresh_status"] = "idle"
        _cycle_lock.release()


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
