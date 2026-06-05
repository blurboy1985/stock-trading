"""Settings + watchlist endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from .. import broker_client as ac
from ..config import settings as env_settings
from ..db import SessionLocal
from ..models import WatchlistItem
from ..services import recommender, runtime_settings
from ..strategies import news_sources

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    weights: dict[str, float] | None = None
    max_position_pct: float | None = None
    max_total_exposure_pct: float | None = None
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    atr_stop_mult: float | None = None
    trailing_stop_enabled: bool | None = None
    trailing_atr_mult: float | None = None
    trailing_stop_dry_run: bool | None = None
    auto_trade: bool | None = None
    buy_threshold: float | None = None
    sell_threshold: float | None = None
    regime_filter: bool | None = None
    regime_hard_gate: float | None = None
    benchmark_symbol: str | None = None
    universe_source: str | None = None
    universe_size: int | None = None
    use_vol_sizing: bool | None = None
    target_risk_pct: float | None = None
    max_sector_exposure_pct: float | None = None
    min_dollar_volume: float | None = None
    min_price: float | None = None
    earnings_blackout_days: int | None = None
    context_signal_mode: str | None = None
    context_veto_threshold: float | None = None
    sentiment_backend: str | None = None
    sentiment_halflife_days: float | None = None
    sentiment_lm_weight: float | None = None
    fundamentals_sector_relative: bool | None = None
    news_sources: list[str] | None = None
    news_scope: str | None = None
    news_per_source_limit: int | None = None
    core_symbol: str | None = None
    core_target_pct: float | None = None
    core_rebalance_threshold_pct: float | None = None


@router.get("")
def get_settings():
    return {
        "settings": runtime_settings.get_all(),
        "watchlist": recommender.get_universe(),
        "news": {
            "all_sources": list(news_sources.ALL_SOURCES),
            "available_sources": news_sources.available_sources(),
        },
        "broker": {
            "name": env_settings.broker,
            "has_credentials": env_settings.has_credentials,
            "is_paper": env_settings.is_paper,
            "trading_enabled": env_settings.trading_enabled,
            "ibkr_host": env_settings.ibkr_host,
            "ibkr_port": env_settings.ibkr_port,
            "ibkr_client_id": env_settings.ibkr_client_id,
            "ibkr_trading_mode": env_settings.ibkr_trading_mode,
            # True only when real-money trading is fully unlocked.
            "live_trading_enabled": env_settings.trading_enabled and env_settings.live_trading and not env_settings.is_paper,
        },
    }


@router.put("")
def update_settings(update: SettingsUpdate):
    payload = {k: v for k, v in update.model_dump().items() if v is not None}
    return {"settings": runtime_settings.set_many(payload)}


def _mirror_to_broker() -> None:
    """Best-effort: broker watchlist sync is a no-op for IBKR."""
    try:
        ac.sync_watchlist(recommender.get_universe())
    except Exception:  # noqa: BLE001 — visibility nicety, not load-bearing
        pass


@router.post("/watchlist/sync")
def sync_watchlist():
    """Sync the current watchlist to the configured broker when supported.

    NOTE: this static route must be declared *before* the ``/watchlist/{symbol}``
    route below — FastAPI matches in declaration order, so otherwise a POST to
    ``/watchlist/sync`` is captured by ``add_symbol`` (adding a bogus "SYNC").
    """
    try:
        return ac.sync_watchlist(recommender.get_universe())
    except ac.BrokerUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Watchlist sync failed: {e}")


@router.post("/watchlist/{symbol}")
def add_symbol(symbol: str):
    symbol = symbol.upper().strip()
    with SessionLocal() as db:
        if not db.scalar(select(WatchlistItem).where(WatchlistItem.symbol == symbol)):
            db.add(WatchlistItem(symbol=symbol))
            db.commit()
    _mirror_to_broker()
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
    _mirror_to_broker()
    return {"watchlist": recommender.get_universe()}
