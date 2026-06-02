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
    # Cap combined exposure to any one GICS sector (correlation guardrail).
    # 0 disables. Best-effort: skipped when a held name's sector is unknown.
    "max_sector_exposure_pct": 0.40,
    "stop_loss_pct": env_settings.stop_loss_pct,
    "take_profit_pct": env_settings.take_profit_pct,
    # Volatility-scaled stops. When >0 the initial stop is placed this many ATRs
    # below the fill (overriding the flat stop_loss_pct); 0 keeps the flat %.
    "atr_stop_mult": 0.0,
    # Live trailing-stop ratchet (paper). When enabled, each scheduler cycle
    # raises a held position's bracket stop toward high_water - k*ATR (it only
    # ever tightens, never loosens). Dry-run logs intended moves without touching
    # orders — flip it off once you've watched it behave. See services/trailing.py.
    "trailing_stop_enabled": False,
    "trailing_atr_mult": 3.0,
    "trailing_stop_dry_run": True,
    "auto_trade": False,  # scheduler auto-proposes trades (user confirms) when true
    "buy_threshold": 0.25,
    "sell_threshold": -0.25,
    # Entry-selectivity gate: require this weight-share of families to vote long
    # before a BUY fires (multi-signal confluence). 0 disables. Backtestable.
    "min_agreement": 0.0,
    # ── Quant controls ────────────────────────────────────────────────
    "regime_filter": True,           # dampen longs in a risk-off market
    # Hard gate: block *new* longs when the regime score is at/below this
    # (capital preservation in clearly risk-off tapes). null/None disables.
    "regime_hard_gate": -0.5,
    "benchmark_symbol": "SPY",       # broad-market proxy for regime + RS
    # ── Universe selection ────────────────────────────────────────────
    "universe_source": "most_active",  # "most_active" (broad scan) | "watchlist"
    "universe_size": 75,               # cap on symbols scored per cycle
    "use_vol_sizing": True,          # volatility-targeted, conviction-scaled sizing
    "target_risk_pct": 0.0025,       # target daily risk per position (ATR-based)
    "min_dollar_volume": 5_000_000,  # liquidity floor: median $-volume/day
    "min_price": 5.0,                # price floor (skip sub-$5 names)
    # Earnings blackout: suppress new BUYs within N days of the next report
    # (gap risk). 0 disables. Live-only — no point-in-time data for backtests.
    "earnings_blackout_days": 5,
    # ── Sentiment / fundamentals tuning ───────────────────────────────
    "sentiment_backend": "lexicon",      # "lexicon" (VADER+LM) or "llm" (ChatGPT/OpenAI)
    "sentiment_halflife_days": 3.0,      # recency decay half-life for headlines
    "sentiment_lm_weight": 0.5,          # blend: Loughran-McDonald vs VADER
    "fundamentals_sector_relative": True,  # value vs sector median (live universe)
    # How sentiment & fundamentals are used. "filter" (default) keeps them OUT of
    # the scored composite — so the return-driving decision is the price stack the
    # backtester validates — and uses them only to veto a BUY when clearly
    # negative. "blend" folds them into the weighted score (legacy, unvalidated).
    "context_signal_mode": "filter",
    "context_veto_threshold": 0.4,  # |score| below -this vetoes a BUY (filter mode)
    # ── News sources (sentiment ingest) ───────────────────────────────
    # Which feeds power the sentiment signal. Yahoo Finance is the default
    # no-key feed; extra sources are fetched per-symbol and merged with
    # event-level de-dup so duplicate coverage can't bias the score.
    "news_sources": ["yfinance"],        # subset of news_sources.ALL_SOURCES
    "news_scope": "watchlist",           # "watchlist" | "universe" for extra sources
    "news_per_source_limit": 15,         # headlines fetched per extra source/symbol
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
