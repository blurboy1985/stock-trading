"""Event-driven, no-look-ahead backtester.

Reuses the *same* signal functions and combination logic as the live recommender
(``scoring`` / ``strategies``) so backtested decisions match live decisions
exactly — now including the cross-sectional momentum rank, the market-regime
filter, and volatility-targeted position sizing.

Model
-----
* Long/flat per symbol; capital sized by volatility target × conviction (or
  equal-weight when ``use_vol_sizing`` is off).
* Decisions at bar ``i`` use only data through bar ``i-1`` (closed bars) and
  execute at bar ``i``'s open, with slippage and per-trade commission applied.
* Optional stop-loss / take-profit are checked intrabar against each bar's
  high/low and fill at the stop/target price.
* Regime + momentum are price-derived, so they replay honestly here. Sentiment &
  fundamentals stay OFF: point-in-time historical news/fundamentals aren't
  available, so including today's values would be look-ahead bias.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ..strategies.cross_section import momentum_signal
from ..strategies.indicators import technical_signal
from ..strategies.momentum import liquidity_ok, momentum_features
from ..strategies.regime import market_regime
from ..strategies.scoring import combine
from ..strategies.volatility import volatility_signal
from .metrics import compute_metrics


@dataclass
class BacktestConfig:
    starting_cash: float = 100_000.0
    weights: dict[str, float] | None = None
    commission: float = 0.0  # $ per trade
    slippage_bps: float = 5.0  # basis points applied to fills
    warmup: int = 50  # bars before trading starts
    position_size_pct: float = 0.0  # 0 => equal-weight across symbols
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    buy_threshold: float = 0.25
    sell_threshold: float = -0.25
    # ── ATR-based exits ───────────────────────────────────────────────
    # When >0 the initial stop is placed ``atr_stop_mult`` ATRs below the
    # fill (volatility-scaled), overriding the flat ``stop_loss_pct``.
    atr_stop_mult: float = 0.0
    # When >0 a chandelier-style trailing stop ratchets up to
    # ``trailing_atr_mult`` ATRs below the highest close seen since entry, so
    # winners run instead of being capped by a fixed take-profit.
    trailing_atr_mult: float = 0.0
    # ── Quant controls (mirror runtime_settings) ──────────────────────
    regime_filter: bool = False
    regime_hard_gate: float | None = None  # block new longs when score <= this
    benchmark_symbol: str | None = None
    use_vol_sizing: bool = False
    target_risk_pct: float = 0.0025
    max_position_pct: float = 0.10
    min_dollar_volume: float = 0.0  # 0 => liquidity guardrail off
    min_price: float = 0.0


@dataclass
class _Position:
    qty: float
    entry_price: float
    entry_date: str
    entry_i: int
    driver: str = "—"
    stop: float | None = None
    target: float | None = None
    atr: float = 0.0  # ATR in price terms at entry (for ATR/trailing stops)
    highest_close: float = 0.0  # peak close since entry, for the trailing stop


@dataclass
class _State:
    cash: float
    positions: dict[str, _Position] = field(default_factory=dict)
    trades: list[dict[str, Any]] = field(default_factory=list)
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    buy_notional: float = 0.0
    invested_bars: int = 0
    attribution: dict[str, float] = field(default_factory=lambda: defaultdict(float))


def _slip(price: float, bps: float, side: str) -> float:
    """Buy fills a touch higher, sell a touch lower."""
    adj = price * bps / 10_000
    return price + adj if side == "buy" else price - adj


def _driver(breakdown: dict[str, Any]) -> str:
    """Family contributing the most to a positive composite (for attribution)."""
    best, best_c = "—", 0.0
    for name, b in breakdown.items():
        contrib = float(b.get("score", 0.0)) * float(b.get("weight", 0.0))
        if contrib > best_c:
            best, best_c = name, contrib
    return best


def _evaluate(
    window: pd.DataFrame,
    weights: dict[str, float] | None,
    momentum=None,
    regime_score: float | None = None,
    regime_hard_gate: float | None = None,
) -> dict[str, Any]:
    """Technical + volatility + (cross-sectional) momentum on the closed window."""
    vol = volatility_signal(window)
    results = {
        "technical": technical_signal(window),
        "volatility": vol,
    }
    if momentum is not None:
        results["momentum"] = momentum
    decision = combine(
        results, weights, regime_score=regime_score,
        regime_hard_gate=regime_hard_gate,
    )
    # Surface ATR (in price terms) for volatility-scaled / trailing stops.
    decision["atr"] = vol.metrics.get("atr")
    return decision


def run_backtest(
    bars_by_symbol: dict[str, pd.DataFrame], config: BacktestConfig
) -> dict[str, Any]:
    symbols = [s for s, df in bars_by_symbol.items() if len(df) > config.warmup + 2]
    if not symbols:
        return {"error": "no symbols with enough history for the chosen window"}

    # Align to a common date index (intersection of all symbols).
    common = None
    for s in symbols:
        idx = bars_by_symbol[s].index
        common = idx if common is None else common.intersection(idx)
    common = common.sort_values()
    if len(common) <= config.warmup + 2:
        return {"error": "overlapping history too short across symbols"}

    aligned = {s: bars_by_symbol[s].reindex(common) for s in symbols}
    bench = aligned.get(config.benchmark_symbol) if config.regime_filter else None
    state = _State(cash=config.starting_cash)
    n = len(common)
    alloc_pct = config.position_size_pct or (1.0 / len(symbols))

    for i in range(config.warmup, n):
        date = common[i]
        date_str = pd.Timestamp(date).isoformat()

        # 1) Intrabar stop-loss / take-profit exits on existing positions.
        for sym in list(state.positions.keys()):
            pos = state.positions[sym]
            bar = aligned[sym].iloc[i]
            if pd.isna(bar["close"]):
                continue
            exit_price = None
            reason = None
            if pos.stop is not None and bar["low"] <= pos.stop:
                # A stop that has ratcheted to/above entry is a trailing exit.
                trailed = config.trailing_atr_mult and pos.stop >= pos.entry_price
                exit_price = pos.stop
                reason = "trailing_stop" if trailed else "stop_loss"
            elif pos.target is not None and bar["high"] >= pos.target:
                exit_price, reason = pos.target, "take_profit"
            if exit_price is not None:
                _close(state, sym, exit_price, date_str, i, config, reason)

        # 2) Cross-sectional momentum + regime from the closed-bar window.
        windows = {s: aligned[s].iloc[:i].dropna() for s in symbols}
        bench_close = None
        if bench is not None:
            bw = bench.iloc[:i].dropna()
            bench_close = bw["close"] if len(bw) else None
        raw_mom = {
            s: momentum_features(w, bench_close).get("raw") for s, w in windows.items()
        }
        mom_signals = momentum_signal(raw_mom)
        regime_score = None
        if config.regime_filter and bench_close is not None and len(bench_close) >= 60:
            regime_score = market_regime(
                bench.iloc[:i].dropna()
            )["score"]

        # 3) Signal-driven actions, executed at this bar's open.
        for sym in symbols:
            window = windows[sym]
            if len(window) < config.warmup:
                continue
            bar = aligned[sym].iloc[i]
            if pd.isna(bar["open"]):
                continue
            decision = _evaluate(
                window, config.weights, mom_signals.get(sym), regime_score,
                config.regime_hard_gate,
            )
            score = decision["score"]
            open_px = float(bar["open"])

            # Liquidity guardrail (optional): block entries in thin names.
            liquid = True
            if config.min_dollar_volume or config.min_price:
                liquid, _ = liquidity_ok(
                    window, config.min_dollar_volume, config.min_price
                )

            holding = sym in state.positions
            if not holding and liquid and score >= config.buy_threshold:
                equity = _equity(state, aligned, i)
                weight = _alloc(config, decision, alloc_pct)
                budget = equity * weight
                fill = _slip(open_px, config.slippage_bps, "buy")
                qty = int(budget // fill)
                if qty > 0 and state.cash >= qty * fill + config.commission:
                    state.cash -= qty * fill + config.commission
                    state.buy_notional += qty * fill
                    atr_dollars = decision.get("atr") or 0.0
                    # Volatility-scaled initial stop when configured, else flat %.
                    if config.atr_stop_mult and atr_dollars > 0:
                        stop = fill - config.atr_stop_mult * atr_dollars
                    elif config.stop_loss_pct:
                        stop = fill * (1 - config.stop_loss_pct)
                    else:
                        stop = None
                    target = (
                        fill * (1 + config.take_profit_pct)
                        if config.take_profit_pct
                        else None
                    )
                    state.positions[sym] = _Position(
                        qty=qty, entry_price=fill, entry_date=date_str, entry_i=i,
                        driver=_driver(decision["breakdown"]), stop=stop, target=target,
                        atr=atr_dollars, highest_close=fill,
                    )
            elif holding and score <= config.sell_threshold:
                fill = _slip(open_px, config.slippage_bps, "sell")
                _close(state, sym, fill, date_str, i, config, "signal")

        # 3b) Ratchet ATR trailing stops off this bar's close. The updated stop
        #     only takes effect from the *next* bar (it's checked intrabar at the
        #     top of the loop), so using this close introduces no look-ahead.
        if config.trailing_atr_mult:
            for sym, pos in state.positions.items():
                close_i = aligned[sym].iloc[i]["close"]
                if pd.isna(close_i):
                    continue
                close_i = float(close_i)
                if close_i > pos.highest_close:
                    pos.highest_close = close_i
                if pos.atr > 0:
                    trail = pos.highest_close - config.trailing_atr_mult * pos.atr
                    pos.stop = trail if pos.stop is None else max(pos.stop, trail)

        # 4) Mark-to-market equity at this bar's close.
        if state.positions:
            state.invested_bars += 1
        state.equity_curve.append(
            {
                "date": date_str,
                "equity": round(_equity(state, aligned, i), 2),
                "invested_pct": round(_invested_pct(state, aligned, i), 4),
            }
        )

    # Liquidate remaining positions at the final close.
    last = n - 1
    last_date = pd.Timestamp(common[last]).isoformat()
    for sym in list(state.positions.keys()):
        close_px = float(aligned[sym].iloc[last]["close"])
        _close(state, sym, close_px, last_date, last, config, "end_of_test")

    benchmark = _buy_and_hold(aligned, symbols, config, common)
    metrics = compute_metrics(
        state.equity_curve, state.trades, config.starting_cash, benchmark
    )
    steps = max(n - config.warmup, 1)
    metrics["exposure_pct"] = round(state.invested_bars / steps, 4)
    metrics["turnover"] = round(state.buy_notional / config.starting_cash, 3)
    metrics["attribution"] = {k: round(v, 2) for k, v in state.attribution.items()}
    return {
        "metrics": metrics,
        "equity_curve": state.equity_curve,
        "benchmark_curve": benchmark,
        "trades": state.trades,
        "symbols": symbols,
    }


def _alloc(config: BacktestConfig, decision: dict[str, Any], equal_w: float) -> float:
    """Capital weight for a new entry: vol-targeted×conviction, or equal-weight."""
    if not config.use_vol_sizing:
        return equal_w
    from ..services.risk import target_weight  # local import avoids a cycle

    return target_weight(
        decision.get("atr_pct"),
        decision.get("conviction", abs(decision["score"])),
        target_risk_pct=config.target_risk_pct,
        max_position_pct=config.max_position_pct,
    )


def _equity(state: _State, aligned: dict[str, pd.DataFrame], i: int) -> float:
    total = state.cash
    for sym, pos in state.positions.items():
        px = aligned[sym].iloc[i]["close"]
        if not pd.isna(px):
            total += pos.qty * float(px)
    return total


def _invested_pct(state: _State, aligned: dict[str, pd.DataFrame], i: int) -> float:
    eq = _equity(state, aligned, i)
    if eq <= 0:
        return 0.0
    held = 0.0
    for sym, pos in state.positions.items():
        px = aligned[sym].iloc[i]["close"]
        if not pd.isna(px):
            held += pos.qty * float(px)
    return held / eq


def _close(
    state: _State,
    sym: str,
    price: float,
    date: str,
    i: int,
    config: BacktestConfig,
    reason: str,
) -> None:
    pos = state.positions.pop(sym)
    proceeds = pos.qty * price - config.commission
    state.cash += proceeds
    pnl = proceeds - pos.qty * pos.entry_price
    state.attribution[pos.driver] += pnl
    state.trades.append(
        {
            "symbol": sym,
            "qty": pos.qty,
            "entry_date": pos.entry_date,
            "entry_price": round(pos.entry_price, 2),
            "exit_date": date,
            "exit_price": round(price, 2),
            "pnl": round(pnl, 2),
            "return_pct": round(price / pos.entry_price - 1, 4),
            "exit_reason": reason,
            "driver": pos.driver,
            "bars_held": i - pos.entry_i,
        }
    )


def _buy_and_hold(
    aligned: dict[str, pd.DataFrame],
    symbols: list[str],
    config: BacktestConfig,
    common: pd.Index,
) -> list[dict[str, Any]]:
    """Equal-weight buy-and-hold benchmark over the same window."""
    start_i = config.warmup
    per_sym = config.starting_cash / len(symbols)
    shares = {}
    for s in symbols:
        px = float(aligned[s].iloc[start_i]["open"])
        shares[s] = per_sym / px if px > 0 else 0.0
    curve = []
    for i in range(start_i, len(common)):
        val = sum(
            shares[s] * float(aligned[s].iloc[i]["close"])
            for s in symbols
            if not pd.isna(aligned[s].iloc[i]["close"])
        )
        curve.append(
            {"date": pd.Timestamp(common[i]).isoformat(), "equity": round(val, 2)}
        )
    return curve
