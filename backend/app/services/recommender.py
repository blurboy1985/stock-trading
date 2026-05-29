"""Recommendation engine: rank a universe of symbols by composite score.

Pulls recent bars + news per symbol, runs the full signal stack (technical,
volatility, sentiment, fundamentals), ranks by composite score, and persists a
Recommendation row per symbol for history/auditing.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select

from .. import alpaca_client as ac
from ..config import settings
from ..db import SessionLocal
from ..models import Recommendation, WatchlistItem
from ..strategies.scoring import evaluate_symbol
from . import runtime_settings


def get_universe() -> list[str]:
    """Watchlist from the DB, falling back to the env-configured default."""
    with SessionLocal() as db:
        rows = db.scalars(select(WatchlistItem.symbol)).all()
    return list(rows) if rows else settings.watchlist_symbols


def _news_by_symbol(symbols: list[str]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {s: [] for s in symbols}
    try:
        for item in ac.get_news(symbols, limit=50):
            for s in item.get("symbols", []):
                if s in out:
                    out[s].append(item)
    except Exception:  # noqa: BLE001 — news is best-effort
        pass
    return out


def generate(persist: bool = True) -> dict[str, Any]:
    """Evaluate the universe and return ranked recommendations."""
    if not settings.has_credentials:
        return {
            "configured": False,
            "message": "Alpaca credentials not set — add them in backend/.env.",
            "recommendations": [],
        }

    universe = get_universe()
    weights = runtime_settings.get("weights")
    news = _news_by_symbol(universe)
    start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=200)

    results: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    for sym in universe:
        try:
            bars = ac.get_bars(sym, start=start)
            if bars.empty:
                errors[sym] = "no bars"
                continue
            decision = evaluate_symbol(sym, bars, news=news.get(sym, []), weights=weights)
            results.append(decision)
        except Exception as e:  # noqa: BLE001 — skip a symbol, keep going
            errors[sym] = f"{type(e).__name__}: {e}"

    # Rank: strongest buys first (desc), strongest sells surface at the bottom.
    results.sort(key=lambda d: d["score"], reverse=True)

    if persist and results:
        with SessionLocal() as db:
            for d in results:
                db.add(
                    Recommendation(
                        symbol=d["symbol"],
                        action=d["action"],
                        score=d["score"],
                        price=d.get("price", 0.0),
                        breakdown=d["breakdown"],
                        reasons=d["reasons"],
                    )
                )
            db.commit()

    buys = [d for d in results if d["action"] == "BUY"]
    sells = [d for d in results if d["action"] == "SELL"]
    return {
        "configured": True,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "recommendations": results,
        "top_buys": buys[:5],
        "top_sells": sells[:5],
        "errors": errors,
    }


def history(symbol: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        q = select(Recommendation).order_by(Recommendation.created_at.desc())
        if symbol:
            q = q.where(Recommendation.symbol == symbol.upper())
        rows = db.scalars(q.limit(limit)).all()
        return [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat(),
                "symbol": r.symbol,
                "action": r.action,
                "score": r.score,
                "price": r.price,
                "reasons": r.reasons,
            }
            for r in rows
        ]
