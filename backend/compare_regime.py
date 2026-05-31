"""Does the #7 regime hard gate cut drawdown in a real bear?

Single full backtests (not walk-forward — we want one long path through the
COVID crash and the 2022 bear) over 2019-2024, all with the proven ATR stop +
trailing exits, varying only the regime hard gate. Reports drawdown and how many
fewer trades the gate let through.
"""
from __future__ import annotations

from app import alpaca_client as ac
from app.backtest.engine import BacktestConfig, run_backtest

SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "JPM", "XOM", "UNH", "SPY"]
START, END, BENCH = "2019-01-01", "2024-12-31", "SPY"


def cfg(gate):
    return BacktestConfig(
        starting_cash=100_000.0, commission=1.0, slippage_bps=5.0, warmup=200,
        regime_filter=True, regime_hard_gate=gate, benchmark_symbol=BENCH,
        use_vol_sizing=True, target_risk_pct=0.0025, max_position_pct=0.10,
        min_dollar_volume=5_000_000, min_price=5.0,
        atr_stop_mult=3.0, trailing_atr_mult=3.0,
    )


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

    scenarios = {"gate OFF": None, "gate -0.5": -0.5, "gate -0.3": -0.3}
    rows = {}
    for name, gate in scenarios.items():
        print(f"  running {name} ...", flush=True)
        rows[name] = run_backtest(bars, cfg(gate))

    labels = [
        ("CAGR", lambda m: f"{m['cagr']*100:.1f}%"),
        ("Total return", lambda m: f"{m['total_return']*100:.1f}%"),
        ("vs Buy&Hold", lambda m: f"{m.get('alpha_vs_benchmark',0)*100:+.1f}%"),
        ("Sharpe", lambda m: f"{m['sharpe']:.2f}"),
        ("Max drawdown", lambda m: f"{m['max_drawdown']*100:.1f}%"),
        ("Exposure", lambda m: f"{m.get('exposure_pct',0)*100:.0f}%"),
        ("# trades", lambda m: f"{m['num_trades']}"),
        ("Profit factor", lambda m: f"{m['profit_factor']:.2f}" if m.get('profit_factor') else "—"),
    ]
    names = list(rows.keys())
    w = 16
    print("\nFULL-PATH 2019-2024 (ATR stop+trail; only the regime gate varies)\n")
    hdr = "Metric".ljust(16) + "".join(n.ljust(w) for n in names)
    print(hdr); print("-" * len(hdr))
    for label, fn in labels:
        line = label.ljust(16)
        for n in names:
            m = rows[n].get("metrics", {})
            line += (fn(m) if "error" not in m else "ERR").ljust(w)
        print(line)


if __name__ == "__main__":
    main()
