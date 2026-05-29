"""Editable runtime settings, persisted in the ``settings`` kv table.

Falls back to the static ``config.settings`` / strategy defaults when a key has
not been overridden. This is what the Settings UI reads and writes so risk
params and signal weights can change without an app restart.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ..config import settings as env_settings
from ..db import SessionLocal
from ..models import Setting
from ..strategies.scoring import DEFAULT_WEIGHTS

# Keys with their hard defaults (env-backed where applicable).
DEFAULTS: dict[str, Any] = {
    "weights": DEFAULT_WEIGHTS,
    "max_position_pct": env_settings.max_position_pct,
    "max_total_exposure_pct": env_settings.max_total_exposure_pct,
    "stop_loss_pct": env_settings.stop_loss_pct,
    "take_profit_pct": env_settings.take_profit_pct,
    "auto_trade": False,  # scheduler auto-executes recommendations when true
    "buy_threshold": 0.25,
    "sell_threshold": -0.25,
}


def get_all() -> dict[str, Any]:
    out = dict(DEFAULTS)
    with SessionLocal() as db:
        for row in db.scalars(select(Setting)).all():
            out[row.key] = row.value
    return out


def get(key: str) -> Any:
    with SessionLocal() as db:
        row = db.get(Setting, key)
        if row is not None:
            return row.value
    return DEFAULTS.get(key)


def set_many(updates: dict[str, Any]) -> dict[str, Any]:
    with SessionLocal() as db:
        for key, value in updates.items():
            if key not in DEFAULTS:
                continue  # ignore unknown keys
            row = db.get(Setting, key)
            if row is None:
                db.add(Setting(key=key, value=value))
            else:
                row.value = value
        db.commit()
    return get_all()
