"""Performance metrics computed from an equity curve and a trade log."""
from __future__ import annotations

import math
from typing import Any

TRADING_DAYS = 252


def compute_metrics(
    equity_curve: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    starting_cash: float,
    benchmark_curve: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Summarize a backtest. ``equity_curve`` items are {date, equity}."""
    if len(equity_curve) < 2:
        return {"error": "not enough data points"}

    equities = [p["equity"] for p in equity_curve]
    final = equities[-1]
    total_return = final / starting_cash - 1

    # Daily simple returns.
    rets = [
        equities[i] / equities[i - 1] - 1
        for i in range(1, len(equities))
        if equities[i - 1] > 0
    ]
    n_days = len(equities)
    years = max(n_days / TRADING_DAYS, 1e-9)
    cagr = (final / starting_cash) ** (1 / years) - 1 if final > 0 else -1.0

    mean_r = sum(rets) / len(rets) if rets else 0.0
    var = sum((r - mean_r) ** 2 for r in rets) / len(rets) if rets else 0.0
    std = math.sqrt(var)
    sharpe = (mean_r / std * math.sqrt(TRADING_DAYS)) if std > 0 else 0.0

    downside = [r for r in rets if r < 0]
    dstd = math.sqrt(sum(r * r for r in downside) / len(downside)) if downside else 0.0
    sortino = (mean_r / dstd * math.sqrt(TRADING_DAYS)) if dstd > 0 else 0.0

    # Max drawdown.
    peak = equities[0]
    max_dd = 0.0
    for e in equities:
        peak = max(peak, e)
        max_dd = min(max_dd, e / peak - 1)

    # Trade stats (closed trades carry a realized pnl).
    closed = [t for t in trades if t.get("pnl") is not None]
    wins = [t for t in closed if t["pnl"] > 0]
    losses = [t for t in closed if t["pnl"] <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)
    win_rate = len(wins) / len(closed) if closed else 0.0
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (
        float("inf") if gross_win > 0 else 0.0
    )

    out = {
        "starting_cash": round(starting_cash, 2),
        "final_equity": round(final, 2),
        "total_return": round(total_return, 4),
        "cagr": round(cagr, 4),
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
        "max_drawdown": round(max_dd, 4),
        "num_trades": len(closed),
        "win_rate": round(win_rate, 4),
        "profit_factor": (
            round(profit_factor, 3) if math.isfinite(profit_factor) else None
        ),
        "avg_win": round(gross_win / len(wins), 2) if wins else 0.0,
        "avg_loss": round(-gross_loss / len(losses), 2) if losses else 0.0,
    }

    if benchmark_curve and len(benchmark_curve) >= 2:
        b0, b1 = benchmark_curve[0]["equity"], benchmark_curve[-1]["equity"]
        out["benchmark_return"] = round(b1 / b0 - 1, 4)
        out["alpha_vs_benchmark"] = round(total_return - (b1 / b0 - 1), 4)

    return out
