"""One-off: walk-forward comparison of exit regimes (baseline vs ATR + trailing).

Fetches real daily bars once, then runs the same walk-forward harness under
several exit configurations so the comparison is apples-to-apples (same entries,
same folds, same out-of-sample stitching). Not part of the app — a proof script.
"""
from __future__ import annotations

import sys

from app import alpaca_client as ac
from app.backtest.engine import BacktestConfig
from app.backtest.walkforward import walk_forward

# Liquid, multi-sector swing names + benchmark; a window spanning bull, the
# 2022 bear, and the 2023-24 recovery so the regime/exit behavior is stress-tested.
SYMBOLS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "JPM", "XOM", "UNH", "SPY",
]
START = "2021-01-01"
END = "2024-12-31"
BENCH = "SPY"
FOLDS = 3
GRID = [0.2, 0.3]


def fetch() -> dict:
    bars = {}
    for s in SYMBOLS:
        try:
            df = ac.get_bars(s, start=START, end=END)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {s}: {e}", file=sys.stderr)
            continue
        if df is not None and len(df):
            bars[s] = df
    return bars


def base_cfg(**kw) -> BacktestConfig:
    # Shared, realistic settings: regime filter on, vol-targeted sizing, the
    # liquidity guardrail, commission + slippage. Only the exit knobs vary.
    defaults = dict(
        starting_cash=100_000.0,
        commission=1.0,
        slippage_bps=5.0,
        warmup=200,  # need 200d history for the regime/long-trend reads
        regime_filter=True,
        benchmark_symbol=BENCH,
        use_vol_sizing=True,
        target_risk_pct=0.0025,
        max_position_pct=0.10,
        min_dollar_volume=5_000_000,
        min_price=5.0,
    )
    defaults.update(kw)
    return BacktestConfig(**defaults)


SCENARIOS = {
    "A: no stops (signal-flip exits only)": base_cfg(),
    "B: fixed 8% stop + 16% target (baseline)": base_cfg(
        stop_loss_pct=0.08, take_profit_pct=0.16
    ),
    "C: ATR stop 3x (no target)": base_cfg(atr_stop_mult=3.0),
    "D: ATR stop 3x + ATR trailing 3x (#1+#2)": base_cfg(
        atr_stop_mult=3.0, trailing_atr_mult=3.0
    ),
    "E: ATR stop 2.5x + trailing 4x (let winners run)": base_cfg(
        atr_stop_mult=2.5, trailing_atr_mult=4.0
    ),
    "F: D + regime hard gate (-0.5) [#7]": base_cfg(
        atr_stop_mult=3.0, trailing_atr_mult=3.0, regime_hard_gate=-0.5
    ),
}

ROWS = [
    ("CAGR", "cagr", "pct"),
    ("Total return", "total_return", "pct"),
    ("Sharpe", "sharpe", "num"),
    ("Sortino", "sortino", "num"),
    ("Max drawdown", "max_drawdown", "pct"),
    ("Win rate", "win_rate", "pct"),
    ("Profit factor", "profit_factor", "num"),
    ("Avg win $", "avg_win", "num"),
    ("Avg loss $", "avg_loss", "num"),
    ("Avg hold (bars)", "avg_holding_period", "num"),
    ("# trades", "num_trades", "int"),
]


def fmt(v, kind):
    if v is None:
        return "—"
    if kind == "pct":
        return f"{v * 100:.1f}%"
    if kind == "int":
        return f"{int(v)}"
    return f"{v:.2f}"


def main() -> None:
    print(f"Fetching {len(SYMBOLS)} symbols {START}..{END} ...", flush=True)
    bars = fetch()
    print(f"Got {len(bars)} symbols with data.\n", flush=True)
    if len(bars) < 3:
        print("Not enough data — aborting.")
        return

    results = {}
    for name, cfg in SCENARIOS.items():
        print(f"  running {name} ...", flush=True)
        wf = walk_forward(bars, cfg, folds=FOLDS, threshold_grid=GRID)
        if "error" in wf:
            print(f"{name}: ERROR {wf['error']}")
            continue
        results[name] = wf["oos_metrics"]

    # Print a comparison table (out-of-sample, stitched across folds).
    names = list(results.keys())
    w = 40
    print(f"OUT-OF-SAMPLE (walk-forward, {FOLDS} folds) — exit-regime comparison\n")
    header = "Metric".ljust(18) + "".join(n[:w].ljust(w) for n in names)
    print(header)
    print("-" * len(header))
    for label, key, kind in ROWS:
        line = label.ljust(18)
        for n in names:
            line += fmt(results[n].get(key), kind).ljust(w)
        print(line)


if __name__ == "__main__":
    main()
