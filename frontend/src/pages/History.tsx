import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Activity } from "../api/client";
import { EquityChart } from "../components/EquityChart";
import { Panel, Stat, Spinner, ErrorBanner, fmtUsd, fmtPct } from "../components/ui";
import { SectionGuide } from "../components/SectionGuide";

const PERIODS: { label: string; value: string }[] = [
  { label: "1M", value: "1M" },
  { label: "3M", value: "3M" },
  { label: "1Y", value: "1A" },
];

export function History() {
  const [period, setPeriod] = useState("1M");

  const hist = useQuery({
    queryKey: ["portfolioHistory", period],
    queryFn: () => api.portfolioHistory(period),
  });
  const activities = useQuery({
    queryKey: ["activities", "history"],
    queryFn: () => api.activities(200),
    refetchInterval: 30_000,
  });

  if (hist.isError) {
    return <ErrorBanner message={(hist.error as Error).message} />;
  }

  const h = hist.data;
  const curve = (h?.points ?? []).map((p) => ({ date: p.time, equity: p.equity }));
  const fills = (activities.data?.activities ?? []).filter(
    (a: Activity) => (a.activity_type || "").toUpperCase() === "FILL",
  );

  return (
    <div className="space-y-5">
      <SectionGuide id="history" />
      <div className="flex items-center justify-between">
        <div className="text-sm text-slate-400">
          Account performance &amp; trade history — read live from your configured broker account.
        </div>
        <div className="flex gap-1">
          {PERIODS.map((p) => (
            <button
              key={p.value}
              onClick={() => setPeriod(p.value)}
              className={`text-xs px-3 py-1.5 rounded-lg border ${
                period === p.value
                  ? "bg-accent/20 border-accent/40 text-accent"
                  : "bg-panel2 border-edge text-slate-300 hover:bg-edge"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat
          label={`P&L (${period.replace("A", "Y")})`}
          value={h?.total_pl != null ? fmtUsd(h.total_pl) : "—"}
          sub={h?.total_pl_pct != null ? fmtPct(h.total_pl_pct) : undefined}
          tone={(h?.total_pl ?? 0) >= 0 ? "up" : "down"}
        />
        <Stat
          label="Period start equity"
          value={h?.base_value != null ? fmtUsd(h.base_value) : "—"}
        />
        <Stat
          label="Current equity"
          value={curve.length ? fmtUsd(curve[curve.length - 1].equity) : "—"}
        />
        <Stat label="Filled trades shown" value={String(fills.length)} />
      </div>

      <Panel title="Equity Curve">
        {hist.isLoading ? (
          <Spinner label="Loading account history…" />
        ) : curve.length > 1 ? (
          <EquityChart strategy={curve} />
        ) : (
          <p className="text-slate-400 text-sm py-6 text-center">
            IBKR Gateway only exposes the current account snapshot here so far;
            not enough stored equity points yet for a curve.
          </p>
        )}
      </Panel>

      <Panel title="Trade History (filled orders)">
        {activities.isLoading ? (
          <Spinner />
        ) : activities.isError ? (
          <ErrorBanner message={(activities.error as Error).message} />
        ) : fills.length === 0 ? (
          <p className="text-slate-400 text-sm py-6 text-center">
            No filled orders yet.
          </p>
        ) : (
          <div className="max-h-[28rem] overflow-auto">
            <table className="w-full text-sm">
              <thead className="text-slate-400 text-xs uppercase sticky top-0 bg-panel">
                <tr className="text-left">
                  <th className="py-2">Date</th>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Qty</th>
                  <th>Type</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {fills.map((a: Activity) => (
                  <tr key={a.id} className="border-t border-edge">
                    <td className="py-1.5 text-slate-400">
                      {a.date ? a.date.slice(0, 10) : "—"}
                    </td>
                    <td className="font-semibold">
                      <Link to={`/ticker/${a.symbol}`} className="hover:text-accent">
                        {a.symbol}
                      </Link>
                    </td>
                    <td className={a.side === "buy" ? "text-buy" : "text-sell"}>{a.side}</td>
                    <td>{a.qty}</td>
                    <td className="text-slate-400">fill @ {a.price}</td>
                    <td className="text-slate-400">{a.order_status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <p className="text-[11px] text-slate-500">
        P&amp;L is the broker account equity change over the selected period
        (realized + unrealized). The same trades and balances appear when you log
        in to TWS/Gateway.
      </p>
    </div>
  );
}
