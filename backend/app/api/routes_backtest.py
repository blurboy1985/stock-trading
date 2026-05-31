"""Backtest endpoints: run a strategy over history and fetch saved runs."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from .. import alpaca_client as ac
from ..backtest.engine import BacktestConfig, run_backtest
from ..backtest.sweep import parameter_sweep
from ..backtest.walkforward import walk_forward
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
    atr_stop_mult: float = 0.0
    trailing_atr_mult: float = 0.0
    position_size_pct: float = 0.0
    warmup: int = 50
    # ── Quant controls ────────────────────────────────────────────────
    regime_filter: bool = False
    regime_hard_gate: float | None = None
    benchmark_symbol: str = "SPY"
    use_vol_sizing: bool = False
    target_risk_pct: float = 0.0025
    max_position_pct: float = 0.10
    min_dollar_volume: float = 0.0
    min_price: float = 0.0
    # Walk-forward / sweep only.
    folds: int = 4


def _fetch_bars(req: "BacktestRequest") -> dict:
    """Fetch aligned bars for the universe (+ benchmark when regime is on)."""
    symbols = [s.strip().upper() for s in req.symbols if s.strip()]
    if not symbols:
        raise HTTPException(status_code=400, detail="no symbols provided")
    # When the regime filter is on, the benchmark must be in the bar set so the
    # engine can read its trend (it also trades, just like SPY in the watchlist).
    if req.regime_filter and req.benchmark_symbol.upper() not in symbols:
        symbols.append(req.benchmark_symbol.upper())

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
    return bars_by_symbol


def _build_config(req: "BacktestRequest", **overrides) -> BacktestConfig:
    return BacktestConfig(
        starting_cash=req.starting_cash,
        weights=req.weights,
        commission=req.commission,
        slippage_bps=req.slippage_bps,
        stop_loss_pct=req.stop_loss_pct,
        take_profit_pct=req.take_profit_pct,
        atr_stop_mult=req.atr_stop_mult,
        trailing_atr_mult=req.trailing_atr_mult,
        position_size_pct=req.position_size_pct,
        warmup=req.warmup,
        regime_filter=req.regime_filter,
        regime_hard_gate=req.regime_hard_gate,
        benchmark_symbol=req.benchmark_symbol.upper(),
        use_vol_sizing=req.use_vol_sizing,
        target_risk_pct=req.target_risk_pct,
        max_position_pct=req.max_position_pct,
        min_dollar_volume=req.min_dollar_volume,
        min_price=req.min_price,
        **overrides,
    )


def _correlation(bars_by_symbol: dict) -> dict:
    """Pairwise correlation of daily returns across the tested universe."""
    import pandas as pd

    closes = pd.DataFrame({s: df["close"] for s, df in bars_by_symbol.items()})
    rets = closes.pct_change().dropna(how="all")
    if rets.shape[1] < 2 or len(rets) < 3:
        return {"symbols": list(bars_by_symbol.keys()), "matrix": []}
    corr = rets.corr().round(2)
    return {
        "symbols": list(corr.columns),
        "matrix": corr.where(corr.notna(), None).values.tolist(),
    }


@router.post("/run")
def run(req: BacktestRequest):
    bars_by_symbol = _fetch_bars(req)
    result = run_backtest(bars_by_symbol, _build_config(req))
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    result["correlation"] = _correlation(bars_by_symbol)

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


@router.post("/walkforward")
def walkforward(req: BacktestRequest):
    """Out-of-sample walk-forward validation (threshold picked per train fold)."""
    bars_by_symbol = _fetch_bars(req)
    result = walk_forward(bars_by_symbol, _build_config(req), folds=req.folds)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/sweep")
def sweep(req: BacktestRequest):
    """Parameter-sensitivity sweep over (buy_threshold × tech/vol tilt)."""
    bars_by_symbol = _fetch_bars(req)
    result = parameter_sweep(bars_by_symbol, _build_config(req))
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
