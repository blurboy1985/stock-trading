"""ORM models: persisted app state.

Alpaca remains the source of truth for the brokerage account; these tables store
the app's own layer — watchlist, recommendation history, signal snapshots, a
local order/trade mirror, and backtest results.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class WatchlistItem(Base):
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    added_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)


class Recommendation(Base):
    """A point-in-time ranked recommendation with its full score breakdown."""

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=_utcnow, index=True
    )
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    action: Mapped[str] = mapped_column(String(8))  # BUY / SELL / HOLD
    score: Mapped[float] = mapped_column(Float)  # composite, [-1, 1]
    price: Mapped[float] = mapped_column(Float)
    # Per-signal sub-scores and human-readable reasons.
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list)


class OrderRecord(Base):
    """Local mirror of an order we submitted (paper or live)."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
    alpaca_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    side: Mapped[str] = mapped_column(String(8))  # buy / sell
    qty: Mapped[float] = mapped_column(Float)
    order_type: Mapped[str] = mapped_column(String(16), default="market")
    limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="new")
    is_paper: Mapped[bool] = mapped_column(default=True)
    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual/auto
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class SignalSnapshot(Base):
    """Raw signal values captured each scheduler tick (for auditing/charts)."""

    __tablename__ = "signal_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=_utcnow, index=True
    )
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
    symbols: Mapped[list[str]] = mapped_column(JSON, default=list)
    start: Mapped[str] = mapped_column(String(32))
    end: Mapped[str] = mapped_column(String(32))
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    equity_curve: Mapped[list[Any]] = mapped_column(JSON, default=list)
    trades: Mapped[list[Any]] = mapped_column(JSON, default=list)


class Setting(Base):
    """Simple key/value store for editable runtime settings (weights, etc.)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
