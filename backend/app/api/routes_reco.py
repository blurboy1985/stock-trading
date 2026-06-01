"""Recommendation endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ..services import recommender, runtime_settings
from ..services.scheduler import LATEST, run_cycle

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


def _universe_signature() -> dict[str, object] | None:
    try:
        cfg = runtime_settings.get_all()
    except Exception:  # noqa: BLE001 — stale detection should not break reads
        return None
    return {
        "benchmark_symbol": cfg.get("benchmark_symbol"),
        "universe_source": cfg.get("universe_source"),
        "universe_size": cfg.get("universe_size"),
    }


def _recommendations_stale() -> bool:
    signature = _universe_signature()
    return signature is not None and LATEST.get("universe_signature") != signature


@router.get("")
def get_recommendations(refresh: bool = Query(False)):
    """Latest recommendations. ``refresh=true`` recomputes synchronously."""
    cycle_result = None
    if refresh:
        cycle_result = run_cycle(force=True)

    message = LATEST.get("message")
    if cycle_result and cycle_result.get("skipped") == "cycle already running":
        message = "A recommendation refresh is already running. This page will update when it finishes."

    return {
        "generated_at": LATEST.get("generated_at"),
        "regime": LATEST.get("regime"),
        "recommendations": LATEST.get("recommendations", []),
        "top_buys": LATEST.get("top_buys", []),
        "top_sells": LATEST.get("top_sells", []),
        "message": message,
        "errors": LATEST.get("errors", {}),
        "refresh_status": LATEST.get("refresh_status", "idle"),
        "universe_signature": LATEST.get("universe_signature"),
        "is_stale": _recommendations_stale(),
    }


@router.get("/history")
def reco_history(symbol: str | None = None, limit: int = 100):
    return {"history": recommender.history(symbol=symbol, limit=limit)}
