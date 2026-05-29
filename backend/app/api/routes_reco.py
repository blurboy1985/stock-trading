"""Recommendation endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ..services import recommender
from ..services.scheduler import LATEST, run_cycle

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.get("")
def get_recommendations(refresh: bool = Query(False)):
    """Latest recommendations. ``refresh=true`` recomputes synchronously."""
    if refresh or not LATEST.get("generated_at"):
        run_cycle(force=True)
    return {
        "generated_at": LATEST.get("generated_at"),
        "recommendations": LATEST.get("recommendations", []),
        "top_buys": LATEST.get("top_buys", []),
        "top_sells": LATEST.get("top_sells", []),
        "auto_actions": LATEST.get("auto_actions", []),
    }


@router.get("/history")
def reco_history(symbol: str | None = None, limit: int = 100):
    return {"history": recommender.history(symbol=symbol, limit=limit)}
