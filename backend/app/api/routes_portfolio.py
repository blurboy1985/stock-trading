"""Portfolio + order endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import broker_client as ac
from ..services import portfolio

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


class OrderRequest(BaseModel):
    symbol: str
    side: str  # buy / sell
    qty: float | None = None  # None => auto-size to max_position_pct
    order_type: str = "market"
    limit_price: float | None = None
    confirm_live: bool = False  # required for real-money orders


@router.get("")
def get_portfolio():
    try:
        return portfolio.snapshot()
    except ac.BrokerUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/orders")
def get_orders(status: str = "all", limit: int = 50):
    try:
        return {"orders": ac.list_orders(status=status, limit=limit)}
    except ac.BrokerUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/activities")
def get_activities(activity_types: str | None = None, page_size: int = 100):
    """Account activity feed (fills, dividends, fees, …) for the Activities tab."""
    try:
        return {"activities": ac.get_activities(activity_types=activity_types, page_size=page_size)}
    except ac.BrokerUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Activities failed: {e}")


@router.post("/order")
def submit_order(req: OrderRequest):
    try:
        return portfolio.place_order(
            symbol=req.symbol,
            side=req.side,
            qty=req.qty,
            order_type=req.order_type,
            limit_price=req.limit_price,
            source="manual",
            confirm_live=req.confirm_live,
        )
    except portfolio.OrderRejected as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ac.BrokerUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Order failed: {e}")


@router.post("/position/{symbol}/close")
def close_position(symbol: str, confirm_live: bool = False):
    """Flatten a position at market (cancels its open bracket first)."""
    try:
        return portfolio.close_position(
            symbol, source="manual", confirm_live=confirm_live
        )
    except portfolio.OrderRejected as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ac.BrokerUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Close failed: {e}")


@router.get("/history")
def portfolio_history(period: str = "1M", timeframe: str = "1D"):
    """Account equity / P&L over time for the History view."""
    try:
        return ac.get_portfolio_history(period=period, timeframe=timeframe)
    except ac.BrokerUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"History failed: {e}")


@router.delete("/order/{order_id}")
def cancel_order(order_id: str):
    try:
        ac.cancel_order(order_id)
        return {"cancelled": order_id}
    except ac.BrokerUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Cancel failed: {e}")
