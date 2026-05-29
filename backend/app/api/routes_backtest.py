"""Backtest endpoints: run a strategy over history and fetch saved runs."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from .. import alpaca_client as ac
from ..backtest.engine import BacktestConfig, run_backtest
from ..db import SessionLocal
from ..models import BacktestRun

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


class BacktestRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1)
    start: str  # ISO date, e.g. "2023-01-01"
    end: str | None = None
    starting_cash: float = 100_000.0
    weights: dict[str, float] | None = None
    commission: float = 0.0
    slippage_bps: float = 5.0
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    position_size_pct: float = 0.0
    warmup: int = 50


@router.post("/run")
def run(req: BacktestRequest):
    symbols = [s.strip().upper() for s in req.symbols if s.strip()]
    if not symbols:
        raise HTTPException(status_code=400, detail="no symbols provided")

    bars_by_symbol = {}
    try:
        for sym in symbols:
            df = ac.get_bars(sym, start=req.start, end=req.end)
            if not df.empty:
                bars_by_symbol[sym] = df
    except ac.AlpacaUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Bars fetch failed: {e}")

    if not bars_by_symbol:
        raise HTTPException(status_code=400, detail="no historical data for symbols")

    config = BacktestConfig(
        starting_cash=req.starting_cash,
        weights=req.weights,
        commission=req.commission,
        slippage_bps=req.slippage_bps,
        stop_loss_pct=req.stop_loss_pct,
        take_profit_pct=req.take_profit_pct,
        position_size_pct=req.position_size_pct,
        warmup=req.warmup,
    )
    result = run_backtest(bars_by_symbol, config)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    with SessionLocal() as db:
        row = BacktestRun(
            symbols=list(bars_by_symbol.keys()),
            start=req.start,
            end=req.end or dt.date.today().isoformat(),
            config=req.model_dump(),
            metrics=result["metrics"],
            equity_curve=result["equity_curve"],
            trades=result["trades"],
        )
        db.add(row)
        db.commit()
        result["run_id"] = row.id
    return result


@router.get("/runs")
def list_runs(limit: int = 25):
    with SessionLocal() as db:
        rows = db.scalars(
            select(BacktestRun).order_by(BacktestRun.created_at.desc()).limit(limit)
        ).all()
        return {
            "runs": [
                {
                    "id": r.id,
                    "created_at": r.created_at.isoformat(),
                    "symbols": r.symbols,
                    "start": r.start,
                    "end": r.end,
                    "metrics": r.metrics,
                }
                for r in rows
            ]
        }


@router.get("/runs/{run_id}")
def get_run(run_id: int):
    with SessionLocal() as db:
        r = db.get(BacktestRun, run_id)
        if not r:
            raise HTTPException(status_code=404, detail="run not found")
        return {
            "id": r.id,
            "created_at": r.created_at.isoformat(),
            "symbols": r.symbols,
            "start": r.start,
            "end": r.end,
            "config": r.config,
            "metrics": r.metrics,
            "equity_curve": r.equity_curve,
            "trades": r.trades,
        }
