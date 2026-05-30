import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  api,
  type BacktestResult,
  type WalkForwardResult,
  type SweepResult,
} from "../api/client";
import { EquityChart } from "../components/EquityChart";
import { Heatmap, divergingColor, correlationColor } from "../components/Heatmap";
import { Panel, Stat, Spinner, ErrorBanner, fmtUsd, fmtPct, fmtNum } from "../components/ui";

export function Backtest() {
  const [symbols, setSymbols] = useState("AAPL,MSFT,SPY");
  const [start, setStart] = useState("2023-01-01");
  const [end, setEnd] = useState("2024-12-31");
  const [stopLoss, setStopLoss] = useState("0.05");
  const [takeProfit, setTakeProfit] = useState("0.15");
  const [cash, setCash] = useState("100000");
  const [regimeFilter, setRegimeFilter] = useState(true);
  const [volSizing, setVolSizing] = useState(true);

  const body = () => ({
    symbols: symbols.split(",").map((s) => s.trim()),
    start,
    end,
    starting_cash: Number(cash),
    stop_loss_pct: stopLoss ? Number(stopLoss) : null,
    take_profit_pct: takeProfit ? Number(takeProfit) : null,
    regime_filter: regimeFilter,
    use_vol_sizing: volSizing,
    benchmark_symbol: "SPY",
  });

  const run = useMutation<BacktestResult>({ mutationFn: () => api.runBacktest(body()) });
  const wf = useMutation<WalkForwardResult>({ mutationFn: () => api.walkForward(body()) });
  const sweep = useMutation<SweepResult>({ mutationFn: () => api.sweep(body()) });

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
        <div className="flex flex-wrap items-center gap-4 mt-3">
          <Field label="Starting cash">
            <input value={cash} onChange={(e) => setCash(e.target.value)} className="inp w-40" />
          </Field>
          <Toggle label="Regime filter" checked={regimeFilter} onChange={setRegimeFilter} />
          <Toggle label="Vol-targeted sizing" checked={volSizing} onChange={setVolSizing} />
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
            <Stat
              label="Exposure"
              value={m.exposure_pct != null ? fmtPct(m.exposure_pct, 0) : "—"}
              sub={m.turnover != null ? `${fmtNum(m.turnover)}× turnover` : undefined}
            />
            <Stat
              label="Avg Hold"
              value={m.avg_holding_period != null ? `${fmtNum(m.avg_holding_period, 0)}d` : "—"}
            />
          </div>

          <Panel title="Equity Curve — Strategy (blue) vs Buy & Hold (grey)">
            <EquityChart strategy={run.data!.equity_curve} benchmark={run.data!.benchmark_curve} />
          </Panel>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <Attribution metrics={m} />
            {run.data!.correlation && run.data!.correlation!.matrix.length > 0 && (
              <Panel title="Universe Correlation (daily returns)">
                <Heatmap
                  rowLabels={run.data!.correlation!.symbols}
                  colLabels={run.data!.correlation!.symbols}
                  values={run.data!.correlation!.matrix}
                  colorFor={correlationColor}
                  format={(v) => (v == null ? "—" : v.toFixed(2))}
                />
                <p className="text-xs text-slate-500 mt-2">
                  High correlation ⇒ less true diversification (positions move together).
                </p>
              </Panel>
            )}
          </div>

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
                    <th>Driver</th>
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
                      <td className="text-slate-400 text-xs capitalize">{t.driver ?? "—"}</td>
                      <td className="text-slate-400 text-xs">{t.exit_reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          {/* ── Validation ──────────────────────────────────────────── */}
          <Panel
            title="Validation — prove the edge holds out-of-sample"
            right={
              <div className="flex gap-2">
                <button
                  onClick={() => wf.mutate()}
                  disabled={wf.isPending}
                  className="bg-accent/20 border border-accent/40 text-accent text-xs px-3 py-1.5 rounded-lg hover:bg-accent/30 disabled:opacity-50"
                >
                  {wf.isPending ? "Running…" : "Walk-forward"}
                </button>
                <button
                  onClick={() => sweep.mutate()}
                  disabled={sweep.isPending}
                  className="bg-accent/20 border border-accent/40 text-accent text-xs px-3 py-1.5 rounded-lg hover:bg-accent/30 disabled:opacity-50"
                >
                  {sweep.isPending ? "Running…" : "Parameter sweep"}
                </button>
              </div>
            }
          >
            {wf.isError && <ErrorBanner message={(wf.error as Error).message} />}
            {sweep.isError && <ErrorBanner message={(sweep.error as Error).message} />}
            {!wf.data && !sweep.data && !wf.isError && !sweep.isError && (
              <p className="text-slate-400 text-sm py-3">
                Walk-forward picks the buy threshold on each train fold and trades it on the
                next unseen fold — a fair out-of-sample estimate. The sweep maps performance
                across thresholds × signal tilts; a broad plateau is robust, a lone spike is
                overfit.
              </p>
            )}

            {wf.data && <WalkForwardView data={wf.data} />}
            {sweep.data && <SweepView data={sweep.data} />}
          </Panel>
        </>
      )}
    </div>
  );
}

function Attribution({ metrics }: { metrics: BacktestResult["metrics"] }) {
  const attr = metrics.attribution ?? {};
  const exits = metrics.by_exit_reason ?? {};
  const entries = Object.entries(attr);
  const max = Math.max(1, ...entries.map(([, v]) => Math.abs(v)));
  return (
    <Panel title="Per-Signal P&L Attribution">
      {entries.length === 0 ? (
        <p className="text-slate-400 text-sm py-3">No closed trades to attribute.</p>
      ) : (
        <div className="space-y-1.5">
          {entries.map(([name, pnl]) => (
            <div key={name} className="flex items-center gap-2 text-sm">
              <div className="w-24 capitalize text-slate-300">{name}</div>
              <div className="flex-1 h-4 bg-panel2 rounded relative overflow-hidden">
                <div
                  className={`absolute top-0 h-full ${pnl >= 0 ? "bg-buy/40" : "bg-sell/40"}`}
                  style={{ width: `${(Math.abs(pnl) / max) * 100}%` }}
                />
              </div>
              <div className={`w-24 text-right font-mono ${pnl >= 0 ? "text-buy" : "text-sell"}`}>
                {fmtUsd(pnl)}
              </div>
            </div>
          ))}
        </div>
      )}
      {Object.keys(exits).length > 0 && (
        <div className="mt-3 pt-3 border-t border-edge text-xs text-slate-400">
          <span className="uppercase tracking-wide">By exit: </span>
          {Object.entries(exits).map(([reason, v]) => (
            <span key={reason} className="mr-3">
              {reason} <span className="text-slate-200">{v.count}</span> (
              <span className={v.pnl >= 0 ? "text-buy" : "text-sell"}>{fmtUsd(v.pnl)}</span>)
            </span>
          ))}
        </div>
      )}
    </Panel>
  );
}

function WalkForwardView({ data }: { data: WalkForwardResult }) {
  const o = data.oos_metrics;
  return (
    <div className="space-y-3 mt-2">
      <div className="text-xs uppercase tracking-wide text-slate-400">
        Out-of-sample (stitched test folds)
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat
          label="OOS Return"
          value={o.total_return != null ? fmtPct(o.total_return) : "—"}
          tone={(o.total_return ?? 0) >= 0 ? "up" : "down"}
        />
        <Stat label="OOS Sharpe" value={fmtNum(o.sharpe)} />
        <Stat label="OOS Max DD" value={fmtPct(o.max_drawdown)} tone="down" />
        <Stat label="OOS Win Rate" value={fmtPct(o.win_rate)} sub={`${o.num_trades} trades`} />
      </div>
      {data.oos_equity_curve.length > 1 && (
        <EquityChart strategy={data.oos_equity_curve} />
      )}
      <table className="w-full text-sm mt-1">
        <thead className="text-slate-400 text-xs uppercase">
          <tr className="text-left">
            <th className="py-1">Fold</th>
            <th>Chosen threshold</th>
            <th>Test return</th>
            <th>Test Sharpe</th>
            <th>Trades</th>
          </tr>
        </thead>
        <tbody>
          {data.folds.map((f) => (
            <tr key={f.fold} className="border-t border-edge">
              <td className="py-1.5">{f.fold}</td>
              <td className="font-mono">{f.chosen_threshold}</td>
              <td
                className={
                  (f.test_metrics.total_return ?? 0) >= 0 ? "text-buy" : "text-sell"
                }
              >
                {f.test_metrics.total_return != null ? fmtPct(f.test_metrics.total_return) : "—"}
              </td>
              <td>{fmtNum(f.test_metrics.sharpe)}</td>
              <td>{f.test_metrics.num_trades ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SweepView({ data }: { data: SweepResult }) {
  // Build a [threshold][tilt] grid of Sharpe values.
  const cellMap = new Map<string, number | null>();
  for (const c of data.cells) cellMap.set(`${c.threshold}|${c.tilt}`, c.sharpe);
  const values = data.thresholds.map((thr) =>
    data.tilts.map((t) => cellMap.get(`${thr}|${t}`) ?? null),
  );
  return (
    <div className="mt-4">
      <div className="text-xs uppercase tracking-wide text-slate-400 mb-2">
        Sharpe by buy-threshold (rows) × technical tilt (cols)
      </div>
      <Heatmap
        rowLabels={data.thresholds}
        colLabels={data.tilts}
        values={values}
        colorFor={(v) => divergingColor(v, 1.5)}
        format={(v) => (v == null ? "—" : v.toFixed(2))}
        rowTitle="thr"
        colTitle="tilt"
      />
      <p className="text-xs text-slate-500 mt-2">
        A broad green plateau ⇒ robust; a single bright cell surrounded by red ⇒ likely overfit.
      </p>
    </div>
  );
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer select-none">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="accent-accent h-4 w-4"
      />
      {label}
    </label>
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
