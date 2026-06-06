"""Shared fixtures: synthetic OHLCV frames with known characteristics."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _ohlcv_from_close(close: np.ndarray) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(close), freq="D", tz="UTC")
    close = pd.Series(close, index=idx)
    high = close * 1.01
    low = close * 0.99
    open_ = close.shift(1).fillna(close.iloc[0])
    vol = pd.Series(1_000_000.0, index=idx)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol}
    )


@pytest.fixture
def uptrend() -> pd.DataFrame:
    # Steadily rising with mild noise.
    n = 120
    base = np.linspace(100, 160, n)
    noise = np.sin(np.linspace(0, 12, n)) * 1.5
    return _ohlcv_from_close(base + noise)


@pytest.fixture
def downtrend() -> pd.DataFrame:
    n = 120
    base = np.linspace(160, 100, n)
    noise = np.sin(np.linspace(0, 12, n)) * 1.5
    return _ohlcv_from_close(base + noise)


@pytest.fixture
def breakout() -> pd.DataFrame:
    # Flat range, then a sharp breakout on the final bar with a volume spike.
    n = 60
    close = np.full(n, 100.0) + np.random.default_rng(0).normal(0, 0.5, n)
    close[-1] = 112.0  # decisive break above the range
    df = _ohlcv_from_close(close)
    df.iloc[-1, df.columns.get_loc("volume")] = 5_000_000.0
    df.iloc[-1, df.columns.get_loc("high")] = 113.0
    return df


# ---------------------------------------------------------------------------
# Ensure the database schema exists before any test runs. On a fresh checkout
# (e.g. CI) there is no SQLite file yet, so settings/proposals tests that read
# the DB via runtime_settings.get_all() would fail with an OperationalError.
# Creating the tables once per session is idempotent and keeps tests hermetic.
# ---------------------------------------------------------------------------
import pytest as _pytest
from app.db import Base as _Base, engine as _engine
import app.models  # noqa: F401  (register models on Base)


@_pytest.fixture(scope="session", autouse=True)
def _ensure_db_schema():
    _Base.metadata.create_all(bind=_engine)
    yield
