"""FastAPI application entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import init_db


def _seed_watchlist() -> None:
    """Populate the watchlist table from the env default on first run so the
    UI can edit it (removing a default symbol works once it's a real row)."""
    from sqlalchemy import select

    from .db import SessionLocal
    from .models import WatchlistItem

    with SessionLocal() as db:
        if db.scalar(select(WatchlistItem).limit(1)) is None:
            for sym in settings.watchlist_symbols:
                db.add(WatchlistItem(symbol=sym))
            db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _seed_watchlist()
    # Scheduler is started here in Phase 4.
    try:
        from .services.scheduler import start_scheduler, stop_scheduler

        start_scheduler()
        yield
        stop_scheduler()
    except ImportError:
        yield


app = FastAPI(
    title="Stock Trading Simulator",
    version="0.1.0",
    description="Multi-signal US-stock paper-trading simulator on Alpaca.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "has_credentials": settings.has_credentials,
        "is_paper": settings.is_paper,
        "live_trading_enabled": settings.live_trading and not settings.is_paper,
    }


# ── Routers ────────────────────────────────────────────────────────────
from .api import routes_market  # noqa: E402

app.include_router(routes_market.router)

# Routers added in later phases; import defensively so the app boots
# even while those modules are still being built.
for _mod in ("routes_reco", "routes_portfolio", "routes_backtest", "routes_settings"):
    try:
        module = __import__(f"app.api.{_mod}", fromlist=["router"])
        app.include_router(module.router)
    except ImportError:
        pass
