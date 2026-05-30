"""Settings + watchlist endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from .. import alpaca_client as ac
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
    sentiment_backend: str | None = None
    sentiment_halflife_days: float | None = None
    sentiment_lm_weight: float | None = None
    fundamentals_sector_relative: bool | None = None


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


def _mirror_to_alpaca() -> None:
    """Best-effort: keep the Alpaca-side watchlist in sync (never blocks)."""
    if not env_settings.has_credentials:
        return
    try:
        ac.sync_watchlist(recommender.get_universe())
    except Exception:  # noqa: BLE001 — visibility nicety, not load-bearing
        pass


@router.post("/watchlist/{symbol}")
def add_symbol(symbol: str):
    symbol = symbol.upper().strip()
    with SessionLocal() as db:
        if not db.scalar(select(WatchlistItem).where(WatchlistItem.symbol == symbol)):
            db.add(WatchlistItem(symbol=symbol))
            db.commit()
    _mirror_to_alpaca()
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
    _mirror_to_alpaca()
    return {"watchlist": recommender.get_universe()}


@router.post("/watchlist/sync")
def sync_watchlist():
    """Push the current watchlist to a named Alpaca watchlist so it's visible
    on the Alpaca site. Returns what was synced."""
    if not env_settings.has_credentials:
        raise HTTPException(status_code=503, detail="Alpaca credentials not configured.")
    try:
        return ac.sync_watchlist(recommender.get_universe())
    except ac.AlpacaUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Watchlist sync failed: {e}")
