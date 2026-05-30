"""Settings + watchlist endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from ..config import settings as env_settings
from ..db import SessionLocal
from ..models import WatchlistItem
from ..services import recommender, runtime_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    weights: dict[str, float] | None = None
    max_position_pct: float | None = None
    max_total_exposure_pct: float | None = None
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    auto_trade: bool | None = None
    buy_threshold: float | None = None
    sell_threshold: float | None = None
    regime_filter: bool | None = None
    benchmark_symbol: str | None = None
    use_vol_sizing: bool | None = None
    target_risk_pct: float | None = None
    min_dollar_volume: float | None = None
    min_price: float | None = None


@router.get("")
def get_settings():
    return {
        "settings": runtime_settings.get_all(),
        "watchlist": recommender.get_universe(),
        "broker": {
            "has_credentials": env_settings.has_credentials,
            "is_paper": env_settings.is_paper,
            # True only when real-money trading is fully unlocked.
            "live_trading_enabled": env_settings.live_trading and not env_settings.is_paper,
        },
    }


@router.put("")
def update_settings(update: SettingsUpdate):
    payload = {k: v for k, v in update.model_dump().items() if v is not None}
    return {"settings": runtime_settings.set_many(payload)}


@router.post("/watchlist/{symbol}")
def add_symbol(symbol: str):
    symbol = symbol.upper().strip()
    with SessionLocal() as db:
        if not db.scalar(select(WatchlistItem).where(WatchlistItem.symbol == symbol)):
            db.add(WatchlistItem(symbol=symbol))
            db.commit()
    return {"watchlist": recommender.get_universe()}


@router.delete("/watchlist/{symbol}")
def remove_symbol(symbol: str):
    symbol = symbol.upper().strip()
    with SessionLocal() as db:
        row = db.scalar(select(WatchlistItem).where(WatchlistItem.symbol == symbol))
        if not row:
            raise HTTPException(status_code=404, detail="symbol not in watchlist")
        db.delete(row)
        db.commit()
    return {"watchlist": recommender.get_universe()}
