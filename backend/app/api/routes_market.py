"""Market data endpoints: quotes, historical bars, news, market clock."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, Query

from .. import alpaca_client as ac

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/clock")
def market_clock():
    try:
        return ac.get_clock()
    except ac.AlpacaUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/quote/{symbol}")
def quote(symbol: str):
    try:
        return ac.get_latest_quote(symbol.upper())
    except ac.AlpacaUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:  # noqa: BLE001 — surface SDK errors as 502
        raise HTTPException(status_code=502, detail=f"Quote fetch failed: {e}")


@router.get("/bars/{symbol}")
def bars(
    symbol: str,
    days: int = Query(180, ge=1, le=2000),
    timeframe: str = Query("1Day"),
):
    """OHLCV bars for the last ``days`` calendar days, charting-ready."""
    start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    try:
        df = ac.get_bars(symbol.upper(), start=start, timeframe=timeframe)
    except ac.AlpacaUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Bars fetch failed: {e}")

    return {
        "symbol": symbol.upper(),
        "bars": [
            {
                "time": idx.isoformat(),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": float(row.volume),
            }
            for idx, row in df.iterrows()
        ],
    }


@router.get("/news")
def news(symbols: str = Query(..., description="Comma-separated tickers"), limit: int = 20):
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    try:
        return {"news": ac.get_news(syms, limit=limit)}
    except ac.AlpacaUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"News fetch failed: {e}")
