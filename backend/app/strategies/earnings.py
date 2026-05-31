"""Earnings-proximity guardrail.

Holding a swing position through an earnings report is an uncontrolled overnight
gamble: a gap can blow straight past a stop (stops don't fill at the stop on a
gap open). So we suppress *new* entries inside a blackout window before the next
report, and flag *held* names approaching one as exit candidates.

This reads the next earnings date straight from the yfinance ``info`` dict the
recommender already fetches for fundamentals — no extra network call. Like
sentiment/fundamentals it has no point-in-time history, so it stays out of the
backtester (live-only); it is a pure risk veto, not a return-seeking signal.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

# Keys yfinance may populate with the (next) earnings date, as unix seconds.
_TS_KEYS = ("earningsTimestampStart", "earningsTimestamp", "earningsTimestampEnd")


def days_to_earnings(info: dict[str, Any] | None, now: dt.datetime | None = None) -> int | None:
    """Calendar days until the next earnings report, or ``None`` if unknown.

    Returns the soonest *future* earnings timestamp found in ``info``. Past-only
    timestamps (the last report) yield ``None`` — we only gate on what's ahead.
    """
    if not info:
        return None
    now = now or dt.datetime.now(dt.timezone.utc)
    soonest: int | None = None
    for key in _TS_KEYS:
        ts = info.get(key)
        if not ts:
            continue
        try:
            when = dt.datetime.fromtimestamp(float(ts), dt.timezone.utc)
        except (ValueError, OSError, OverflowError):
            continue
        days = (when - now).days
        if days >= 0 and (soonest is None or days < soonest):
            soonest = days
    return soonest


def earnings_blackout(
    info: dict[str, Any] | None, within_days: int, now: dt.datetime | None = None
) -> tuple[bool, str]:
    """``(in_blackout, reason)`` — True when earnings land within ``within_days``.

    ``within_days <= 0`` disables the gate (always returns ``(False, "")``).
    """
    if within_days <= 0:
        return False, ""
    d = days_to_earnings(info, now)
    if d is not None and d <= within_days:
        when = "today/imminent" if d == 0 else f"in {d}d"
        return True, f"earnings {when} (gap risk)"
    return False, ""
