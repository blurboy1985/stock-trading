import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
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
  const orders = useQuery({
    queryKey: ["orders", "closed"],
    queryFn: () => api.orders("closed"),
    refetchInterval: 30_000,
  });

  if (hist.isError) {
    return <ErrorBanner message={(hist.error as Error).message} />;
  }

  const h = hist.data;
  const curve = (h?.points ?? []).map((p) => ({ date: p.time, equity: p.equity }));
  const closed = (orders.data?.orders ?? []).filter(
    (o: any) => o.status === "filled" || Number(o.filled_qty) > 0,
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
        <Stat label="Filled trades shown" value={String(closed.length)} />
      </div>

      <Panel title="Equity Curve">
        {hist.isLoading ? (
          <Spinner label="Loading account history…" />
        ) : curve.length > 1 ? (
          <EquityChart strategy={curve} />
        ) : (
          <p className="text-slate-400 text-sm py-6 text-center">
            Not enough account history yet for this period.
          </p>
        )}
      </Panel>

      <Panel title="Trade History (filled orders)">
        {orders.isLoading ? (
          <Spinner />
        ) : closed.length === 0 ? (
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
                {closed.map((o: any) => (
                  <tr key={o.id} className="border-t border-edge">
                    <td className="py-1.5 text-slate-400">
                      {o.submitted_at ? o.submitted_at.slice(0, 10) : "—"}
                    </td>
                    <td className="font-semibold">
                      <Link to={`/ticker/${o.symbol}`} className="hover:text-accent">
                        {o.symbol}
                      </Link>
                    </td>
                    <td className={o.side === "buy" ? "text-buy" : "text-sell"}>{o.side}</td>
                    <td>{o.filled_qty || o.qty}</td>
                    <td className="text-slate-400">{o.type}</td>
                    <td className="text-slate-400">{o.status}</td>
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
