"""Auto-trade proposal endpoints: review, confirm, and reject pending trades."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .. import alpaca_client as ac
from ..services import proposals

router = APIRouter(prefix="/api/proposals", tags=["proposals"])


@router.get("")
def get_proposals(status: str | None = Query("pending")):
    """List proposals, newest first. ``status=`` (empty) returns all statuses."""
    return {"proposals": proposals.list_proposals(status or None)}


@router.post("/confirm-all")
def confirm_all():
    """Execute every confirmable (non-blocked) pending proposal."""
    try:
        return proposals.confirm_all()
    except ac.AlpacaUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/{proposal_id}/confirm")
def confirm(proposal_id: int):
    try:
        return proposals.confirm(proposal_id)
    except proposals.ProposalNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except proposals.ProposalError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ac.AlpacaUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/{proposal_id}/reject")
def reject(proposal_id: int):
    try:
        return proposals.reject(proposal_id)
    except proposals.ProposalNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except proposals.ProposalError as e:
        raise HTTPException(status_code=400, detail=str(e))
