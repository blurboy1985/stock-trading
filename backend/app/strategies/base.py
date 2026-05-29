"""Shared contract for all signal families.

Every signal function returns a :class:`SignalResult` whose ``score`` is
normalized to ``[-1, +1]`` (negative = bearish/sell, positive = bullish/buy).
This uniform shape lets ``scoring.combine`` blend any mix of signals with
configurable weights and lets the backtester reuse the exact same functions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SignalResult:
    score: float = 0.0  # normalized to [-1, 1]
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def clamp(self) -> "SignalResult":
        self.score = max(-1.0, min(1.0, self.score))
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "reasons": self.reasons,
            "metrics": {
                k: (round(v, 4) if isinstance(v, float) else v)
                for k, v in self.metrics.items()
            },
        }


def clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))
