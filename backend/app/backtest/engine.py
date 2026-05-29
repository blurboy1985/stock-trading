"""Event-driven, no-look-ahead backtester.

Reuses the *same* signal functions as the live recommender (``scoring`` /
``strategies``) so backtested decisions match live decisions exactly.

Model
-----
* Long/flat per symbol; capital split equally across the symbol universe.
* Decisions at bar ``i`` use only data through bar ``i-1`` (closed bars) and
  execute at bar ``i``'s open, with slippage and per-trade commission applied.
* Optional stop-loss / take-profit are checked intrabar against each bar's
  high/low and fill at the stop/target price.
* Sentiment & fundamentals are OFF by default: point-in-time historical news and
  fundamentals aren't available, so including today's values would be
  look-ahead bias. Backtests therefore validate the technical + volatility core.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ..strategies.scoring import combine
from ..strategies.indicators import technical_signal
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


@dataclass
class _Position:
    qty: float
    entry_price: float
    entry_date: str
    stop: float | None = None
    target: float | None = None


@dataclass
class _State:
    cash: float
    positions: dict[str, _Position] = field(default_factory=dict)
    trades: list[dict[str, Any]] = field(default_factory=list)
    equity_curve: list[dict[str, Any]] = field(default_factory=list)


def _slip(price: float, bps: float, side: str) -> float:
    """Buy fills a touch higher, sell a touch lower."""
    adj = price * bps / 10_000
    return price + adj if side == "buy" else price - adj


def _evaluate(window: pd.DataFrame, weights: dict[str, float] | None) -> dict[str, Any]:
    """Technical + volatility composite on the closed-bar window."""
    results = {
        "technical": technical_signal(window),
        "volatility": volatility_signal(window),
    }
    return combine(results, weights)


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
                exit_price, reason = pos.stop, "stop_loss"
            elif pos.target is not None and bar["high"] >= pos.target:
                exit_price, reason = pos.target, "take_profit"
            if exit_price is not None:
                _close(state, sym, exit_price, date_str, config, reason)

        # 2) Signal-driven actions, executed at this bar's open.
        for sym in symbols:
            window = aligned[sym].iloc[:i].dropna()  # closed bars only
            if len(window) < config.warmup:
                continue
            bar = aligned[sym].iloc[i]
            if pd.isna(bar["open"]):
                continue
            decision = _evaluate(window, config.weights)
            score = decision["score"]
            open_px = float(bar["open"])

            holding = sym in state.positions
            if not holding and score >= config.buy_threshold:
                equity = _equity(state, aligned, i)
                budget = equity * alloc_pct
                fill = _slip(open_px, config.slippage_bps, "buy")
                qty = int(budget // fill)
                if qty > 0 and state.cash >= qty * fill + config.commission:
                    state.cash -= qty * fill + config.commission
                    stop = fill * (1 - config.stop_loss_pct) if config.stop_loss_pct else None
                    target = (
                        fill * (1 + config.take_profit_pct)
                        if config.take_profit_pct
                        else None
                    )
                    state.positions[sym] = _Position(
                        qty=qty, entry_price=fill, entry_date=date_str,
                        stop=stop, target=target,
                    )
            elif holding and score <= config.sell_threshold:
                fill = _slip(open_px, config.slippage_bps, "sell")
                _close(state, sym, fill, date_str, config, "signal")

        # 3) Mark-to-market equity at this bar's close.
        state.equity_curve.append(
            {"date": date_str, "equity": round(_equity(state, aligned, i), 2)}
        )

    # Liquidate remaining positions at the final close.
    last = n - 1
    last_date = pd.Timestamp(common[last]).isoformat()
    for sym in list(state.positions.keys()):
        close_px = float(aligned[sym].iloc[last]["close"])
        _close(state, sym, close_px, last_date, config, "end_of_test")

    benchmark = _buy_and_hold(aligned, symbols, config, common)
    metrics = compute_metrics(
        state.equity_curve, state.trades, config.starting_cash, benchmark
    )
    return {
        "metrics": metrics,
        "equity_curve": state.equity_curve,
        "benchmark_curve": benchmark,
        "trades": state.trades,
        "symbols": symbols,
    }


def _equity(state: _State, aligned: dict[str, pd.DataFrame], i: int) -> float:
    total = state.cash
    for sym, pos in state.positions.items():
        px = aligned[sym].iloc[i]["close"]
        if not pd.isna(px):
            total += pos.qty * float(px)
    return total


def _close(
    state: _State,
    sym: str,
    price: float,
    date: str,
    config: BacktestConfig,
    reason: str,
) -> None:
    pos = state.positions.pop(sym)
    proceeds = pos.qty * price - config.commission
    state.cash += proceeds
    pnl = proceeds - pos.qty * pos.entry_price
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
