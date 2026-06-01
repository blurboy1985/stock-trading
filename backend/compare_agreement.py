"""Does requiring multi-signal agreement to enter improve the edge?

Walk-forward sweep of the entry-selectivity gate (`min_agreement`) on top of the
proven ATR stop + trailing exits. A higher gate trades less but only on
confluence — we want to see whether that lifts OOS Sharpe / profit factor or just
starves the strategy of trades.
"""
from __future__ import annotations

from app import broker_client as ac
from app.backtest.engine import BacktestConfig
from app.backtest.walkforward import walk_forward

SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "JPM", "XOM", "UNH", "SPY"]
START, END, BENCH = "2021-01-01", "2024-12-31", "SPY"
FOLDS, GRID = 3, [0.2, 0.3]
GATES = [0.0, 0.4, 0.5, 0.6, 0.7, 0.8]


def cfg(min_agreement: float) -> BacktestConfig:
    return BacktestConfig(
        starting_cash=100_000.0, commission=1.0, slippage_bps=5.0, warmup=200,
        regime_filter=True, benchmark_symbol=BENCH, use_vol_sizing=True,
        target_risk_pct=0.0025, max_position_pct=0.10,
        min_dollar_volume=5_000_000, min_price=5.0,
        atr_stop_mult=3.0, trailing_atr_mult=3.0,
        min_agreement=min_agreement,
    )


ROWS = [
    ("CAGR", "cagr", "pct"), ("Total return", "total_return", "pct"),
    ("Sharpe", "sharpe", "num"), ("Sortino", "sortino", "num"),
    ("Max drawdown", "max_drawdown", "pct"), ("Win rate", "win_rate", "pct"),
    ("Profit factor", "profit_factor", "num"), ("# trades", "num_trades", "int"),
]


def fmt(v, kind):
    if v is None:
        return "-"
    if kind == "pct":
        return f"{v * 100:.1f}%"
    if kind == "int":
        return f"{int(v)}"
    return f"{v:.2f}"


def main():
    print(f"Fetching {len(SYMBOLS)} symbols {START}..{END} ...", flush=True)
    bars = {}
    for s in SYMBOLS:
        try:
            df = ac.get_bars(s, start=START, end=END)
            if len(df):
                bars[s] = df
        except Exception as e:  # noqa: BLE001
            print(f"  ! {s}: {e}", flush=True)
    print(f"Got {len(bars)} symbols.\n", flush=True)

    results = {}
    for g in GATES:
        label = f"agree>={int(g*100)}%" if g else "no gate"
        print(f"  running {label} ...", flush=True)
        wf = walk_forward(bars, cfg(g), folds=FOLDS, threshold_grid=GRID)
        results[label] = wf.get("oos_metrics", {"error": wf.get("error")})

    names = list(results.keys())
    w = 14
    print(f"\nOOS walk-forward ({FOLDS} folds) - entry agreement gate sweep\n")
    hdr = "Metric".ljust(16) + "".join(n.ljust(w) for n in names)
    print(hdr); print("-" * len(hdr))
    for label, key, kind in ROWS:
        line = label.ljust(16)
        for n in names:
            m = results[n]
            line += (fmt(m.get(key), kind) if "error" not in m else "ERR").ljust(w)
        print(line)


if __name__ == "__main__":
    main()
