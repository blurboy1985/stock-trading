import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, type BacktestResult } from "../api/client";
import { EquityChart } from "../components/EquityChart";
import { Panel, Stat, Spinner, ErrorBanner, fmtUsd, fmtPct, fmtNum } from "../components/ui";

export function Backtest() {
  const [symbols, setSymbols] = useState("AAPL,MSFT,SPY");
  const [start, setStart] = useState("2023-01-01");
  const [end, setEnd] = useState("2024-12-31");
  const [stopLoss, setStopLoss] = useState("0.05");
  const [takeProfit, setTakeProfit] = useState("0.15");
  const [cash, setCash] = useState("100000");

  const run = useMutation<BacktestResult>({
    mutationFn: () =>
      api.runBacktest({
        symbols: symbols.split(",").map((s) => s.trim()),
        start,
        end,
        starting_cash: Number(cash),
        stop_loss_pct: stopLoss ? Number(stopLoss) : null,
        take_profit_pct: takeProfit ? Number(takeProfit) : null,
      }),
  });

  const m = run.data?.metrics;

  return (
    <div className="space-y-5">
      <Panel title="Backtest Configuration">
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3 items-end">
          <Field label="Symbols" className="col-span-2">
            <input value={symbols} onChange={(e) => setSymbols(e.target.value)} className="inp" />
          </Field>
          <Field label="Start">
            <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="inp" />
          </Field>
          <Field label="End">
            <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="inp" />
          </Field>
          <Field label="Stop loss">
            <input value={stopLoss} onChange={(e) => setStopLoss(e.target.value)} className="inp" />
          </Field>
          <Field label="Take profit">
            <input value={takeProfit} onChange={(e) => setTakeProfit(e.target.value)} className="inp" />
          </Field>
        </div>
        <div className="flex items-center gap-3 mt-3">
          <Field label="Starting cash">
            <input value={cash} onChange={(e) => setCash(e.target.value)} className="inp w-40" />
          </Field>
          <button
            onClick={() => run.mutate()}
            disabled={run.isPending}
            className="self-end bg-accent text-white px-5 py-2 rounded-lg hover:bg-accent/80 disabled:opacity-50"
          >
            {run.isPending ? "Running…" : "Run backtest"}
          </button>
        </div>
      </Panel>

      {run.isPending && <Spinner label="Replaying history…" />}
      {run.isError && <ErrorBanner message={(run.error as Error).message} />}

      {m && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Stat
              label="Total Return"
              value={fmtPct(m.total_return)}
              tone={m.total_return >= 0 ? "up" : "down"}
              sub={`Final ${fmtUsd(m.final_equity)}`}
            />
            <Stat
              label="vs Buy & Hold"
              value={m.alpha_vs_benchmark != null ? fmtPct(m.alpha_vs_benchmark) : "—"}
              tone={(m.alpha_vs_benchmark ?? 0) >= 0 ? "up" : "down"}
              sub={m.benchmark_return != null ? `B&H ${fmtPct(m.benchmark_return)}` : undefined}
            />
            <Stat label="Sharpe" value={fmtNum(m.sharpe)} sub={`Sortino ${fmtNum(m.sortino)}`} />
            <Stat
              label="Max Drawdown"
              value={fmtPct(m.max_drawdown)}
              tone="down"
              sub={`CAGR ${fmtPct(m.cagr)}`}
            />
            <Stat label="Win Rate" value={fmtPct(m.win_rate)} sub={`${m.num_trades} trades`} />
            <Stat
              label="Profit Factor"
              value={m.profit_factor != null ? fmtNum(m.profit_factor) : "∞"}
            />
            <Stat label="Avg Win" value={fmtUsd(m.avg_win)} tone="up" />
            <Stat label="Avg Loss" value={fmtUsd(m.avg_loss)} tone="down" />
          </div>

          <Panel title="Equity Curve — Strategy (blue) vs Buy & Hold (grey)">
            <EquityChart
              strategy={run.data!.equity_curve}
              benchmark={run.data!.benchmark_curve}
            />
          </Panel>

          <Panel title={`Trades (${run.data!.trades.length})`}>
            <div className="max-h-80 overflow-auto">
              <table className="w-full text-sm">
                <thead className="text-slate-400 text-xs uppercase sticky top-0 bg-panel">
                  <tr className="text-left">
                    <th className="py-2">Symbol</th>
                    <th>Entry</th>
                    <th>Exit</th>
                    <th>Return</th>
                    <th>P&L</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {run.data!.trades.map((t, i) => (
                    <tr key={i} className="border-t border-edge">
                      <td className="py-1.5 font-semibold">{t.symbol}</td>
                      <td>{t.entry_date.slice(0, 10)} @ {fmtUsd(t.entry_price)}</td>
                      <td>{t.exit_date.slice(0, 10)} @ {fmtUsd(t.exit_price)}</td>
                      <td className={t.return_pct >= 0 ? "text-buy" : "text-sell"}>
                        {fmtPct(t.return_pct)}
                      </td>
                      <td className={t.pnl >= 0 ? "text-buy" : "text-sell"}>{fmtUsd(t.pnl)}</td>
                      <td className="text-slate-400 text-xs">{t.exit_reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </>
      )}
    </div>
  );
}

function Field({
  label,
  children,
  className = "",
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label className={`block ${className}`}>
      <span className="text-xs text-slate-400">{label}</span>
      {children}
    </label>
  );
}
