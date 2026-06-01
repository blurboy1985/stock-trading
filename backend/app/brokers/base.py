"""Broker-neutral exceptions and helpers."""
from __future__ import annotations

from typing import Any


class BrokerUnavailable(RuntimeError):
    """Raised when the configured broker cannot service a request."""


def enumval(v: Any, default: Any = "") -> Any:
    if v is None:
        return default
    value = getattr(v, "value", v)
    return str(value).lower() if value is not None else default


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default
