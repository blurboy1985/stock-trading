"""Recommendation engine: rank a universe of symbols by risk-adjusted score.

Pulls recent bars + news per symbol, derives the market regime and a
cross-sectional momentum ranking, runs the full signal stack (technical,
volatility, momentum, sentiment, fundamentals), then ranks by a *risk-adjusted*
score (conviction-weighted, volatility-penalized) and persists a Recommendation
row per symbol for history/auditing.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select

from .. import alpaca_client as ac
from ..config import settings
from ..db import SessionLocal
from ..models import Recommendation, WatchlistItem
from ..strategies import fundamentals as fundamentals_mod
from ..strategies import regime as regime_mod
from ..strategies.cross_section import momentum_signal
from ..strategies.momentum import liquidity_ok, momentum_features
from ..strategies.scoring import evaluate_symbol
from . import risk, runtime_settings

# Floor mirrors risk._ATR_FLOOR so ranking can't divide by a near-zero vol.
_ATR_FLOOR = 0.005


def get_universe() -> list[str]:
    """The user's watchlist from the DB, falling back to the env default.

    This is the *watchlist* (used for the Alpaca sync and Settings views), not
    necessarily the full set of symbols scored each cycle — see
    :func:`build_universe`.
    """
    with SessionLocal() as db:
        rows = db.scalars(select(WatchlistItem.symbol)).all()
    return list(rows) if rows else settings.watchlist_symbols


def build_universe(cfg: dict[str, Any]) -> tuple[list[str], set[str]]:
    """Compose the set of symbols to score this cycle and the watchlist subset.

    With ``universe_source == "most_active"`` (the default) the universe is the
    day's most-active US stocks, *always* unioned with the full watchlist and the
    benchmark (so those are scored + starred and the regime/RS baselines stay
    anchored), deduped and capped at ``universe_size``. Falls back to a
    watchlist-only universe when the source is set to ``"watchlist"`` or the
    screener is unavailable. Returns ``(universe, watchlist_set)``.
    """
    watchlist = [s.upper() for s in get_universe()]
    wl_set = set(watchlist)
    bench = (cfg.get("benchmark_symbol") or "SPY").upper()
    # Watchlist + benchmark are mandatory members, in that order.
    must = list(dict.fromkeys([*watchlist, bench]))

    if cfg.get("universe_source", "most_active") != "most_active":
        return must, wl_set

    size = int(cfg.get("universe_size", 75))
    movers = [m.upper() for m in ac.get_most_actives(top=size)]
    if not movers:  # screener outage → watchlist-only (current behavior)
        return must, wl_set

    must_set = set(must)
    extra = [m for m in dict.fromkeys(movers) if m not in must_set]
    room = max(0, size - len(must))
    return must + extra[:room], wl_set


def _news_by_symbol(symbols: list[str]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {s: [] for s in symbols}
    try:
        for item in ac.get_news(symbols, limit=50):
            for s in item.get("symbols", []):
                if s in out:
                    out[s].append(item)
    except Exception:  # noqa: BLE001 — news is best-effort
        pass
    return out


def _equity_best_effort() -> float | None:
    try:
        return float(ac.get_account()["equity"])
    except Exception:  # noqa: BLE001 — sizing hint is optional
        return None


def generate(persist: bool = True) -> dict[str, Any]:
    """Evaluate the universe and return ranked recommendations."""
    if not settings.has_credentials:
        return {
            "configured": False,
            "message": "Alpaca credentials not set — add them in backend/.env.",
            "recommendations": [],
        }

    cfg = runtime_settings.get_all()
    weights = cfg["weights"]
    universe, watchlist_set = build_universe(cfg)
    news = _news_by_symbol(universe)
    start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=400)

    # With the LLM sentiment backend, score every distinct headline in one
    # Claude call up front. The per-symbol scoring below then hits the cache
    # instead of firing a separate ~5s CLI call per symbol (which turned a
    # refresh into a multi-minute hang).
    if cfg["sentiment_backend"] == "llm":
        from ..strategies import sentiment_llm

        all_items = [item for items in news.values() for item in items]
        sentiment_llm.prewarm(all_items)

    # 1) Batch-fetch bars in a single request (needed up front for breadth +
    #    cross-sectional momentum). Batching keeps a large-universe scan fast.
    errors: dict[str, str] = {}
    try:
        bars_by_symbol: dict[str, Any] = ac.get_bars_multi(universe, start=start)
    except Exception as e:  # noqa: BLE001 — fall back to per-symbol below
        bars_by_symbol = {}
        errors["_bars_batch"] = f"{type(e).__name__}: {e}"
    for sym in universe:
        if sym not in bars_by_symbol:
            errors.setdefault(sym, "no bars")

    # 2) Market regime from the benchmark (+ breadth across the universe).
    bench_sym = cfg["benchmark_symbol"]
    bench_bars = bars_by_symbol.get(bench_sym)
    if bench_bars is None:
        try:
            bench_bars = ac.get_bars(bench_sym, start=start)
        except Exception:  # noqa: BLE001
            bench_bars = None
    breadth = regime_mod.breadth_above_trend(bars_by_symbol)
    regime = (
        regime_mod.market_regime(bench_bars, breadth)
        if (cfg["regime_filter"] and bench_bars is not None and len(bench_bars))
        else {"label": "neutral", "score": 0.0, "multiplier": 1.0, "reasons": [], "metrics": {}}
    )
    regime_score = regime["score"] if cfg["regime_filter"] else None

    # 3) Cross-sectional momentum ranking across the universe.
    bench_close = bench_bars["close"] if bench_bars is not None else None
    raw_mom = {
        s: momentum_features(df, bench_close).get("raw")
        for s, df in bars_by_symbol.items()
    }
    mom_signals = momentum_signal(raw_mom)

    # 3b) Fundamentals: fetch raw info once per symbol, derive sector-median
    #     baselines so valuation is scored relative to peers (live universe).
    infos = {s: fundamentals_mod.get_info(s) for s in bars_by_symbol}
    baselines = (
        fundamentals_mod.build_sector_baselines(infos)
        if cfg["fundamentals_sector_relative"]
        else {}
    )

    # 4) Evaluate each symbol with regime, momentum, and a liquidity guardrail.
    equity = _equity_best_effort()
    results: list[dict[str, Any]] = []
    for sym, df in bars_by_symbol.items():
        try:
            ok, why = liquidity_ok(df, cfg["min_dollar_volume"], cfg["min_price"])
            info = infos.get(sym, {})
            sector_baseline = baselines.get(info.get("sector")) if info else None
            decision = evaluate_symbol(
                sym, df,
                news=news.get(sym, []),
                weights=weights,
                momentum=mom_signals.get(sym),
                regime_score=regime_score,
                liquidity_warning=None if ok else why,
                sentiment_backend=cfg["sentiment_backend"],
                sentiment_halflife_days=cfg["sentiment_halflife_days"],
                sentiment_lm_weight=cfg["sentiment_lm_weight"],
                sector_baseline=sector_baseline,
                info=info,
            )
            decision["in_watchlist"] = sym in watchlist_set
            _enrich(decision, regime, cfg, equity)
            results.append(decision)
        except Exception as e:  # noqa: BLE001
            errors[sym] = f"{type(e).__name__}: {e}"

    # 5) Rank by risk-adjusted score: conviction-weighted, volatility-penalized.
    results.sort(key=lambda d: d.get("rank_score", d["score"]), reverse=True)

    if persist and results:
        # With a broad universe, persist only the top-ranked names plus every
        # watchlist name, so the history table doesn't balloon each cycle.
        to_persist = [
            d for i, d in enumerate(results)
            if i < 25 or d.get("in_watchlist")
        ]
        with SessionLocal() as db:
            for d in to_persist:
                db.add(
                    Recommendation(
                        symbol=d["symbol"],
                        action=d["action"],
                        score=d["score"],
                        price=d.get("price", 0.0),
                        breakdown=d["breakdown"],
                        reasons=d["reasons"],
                        conviction=d.get("conviction"),
                        rank_score=d.get("rank_score"),
                        regime=regime["label"],
                    )
                )
            db.commit()

    buys = [d for d in results if d["action"] == "BUY"]
    sells = [d for d in results if d["action"] == "SELL"]
    return {
        "configured": True,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "regime": regime,
        "recommendations": results,
        "top_buys": buys[:5],
        "top_sells": sells[:5],
        "errors": errors,
    }


def _enrich(
    decision: dict[str, Any], regime: dict[str, Any], cfg: dict[str, Any],
    equity: float | None,
) -> None:
    """Attach risk-adjusted rank score and a suggested position size."""
    decision["regime_label"] = regime["label"]
    score = decision["score"]
    conviction = decision.get("conviction", abs(score))
    atr_pct = decision.get("atr_pct") or _ATR_FLOOR
    # Risk-adjusted rank: reward conviction, penalize volatility.
    decision["rank_score"] = round(score * conviction / max(atr_pct, _ATR_FLOOR), 4)

    if cfg["use_vol_sizing"]:
        weight = risk.target_weight(
            decision.get("atr_pct"), conviction,
            target_risk_pct=cfg["target_risk_pct"],
            max_position_pct=cfg["max_position_pct"],
        )
    else:
        weight = cfg["max_position_pct"]
    decision["suggested_weight_pct"] = round(weight, 4)
    price = decision.get("price") or 0.0
    if equity and price > 0 and decision["action"] == "BUY":
        decision["suggested_qty"] = int((equity * weight) // price)
    else:
        decision["suggested_qty"] = None


def history(symbol: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        q = select(Recommendation).order_by(Recommendation.created_at.desc())
        if symbol:
            q = q.where(Recommendation.symbol == symbol.upper())
        rows = db.scalars(q.limit(limit)).all()
        return [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat(),
                "symbol": r.symbol,
                "action": r.action,
                "score": r.score,
                "price": r.price,
                "reasons": r.reasons,
            }
            for r in rows
        ]
