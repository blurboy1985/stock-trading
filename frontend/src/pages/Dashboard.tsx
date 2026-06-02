import { useState } from "react";
import type { ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Account, Position, OrderRow, Activity } from "../api/client";
import {
  Panel,
  Stat,
  Spinner,
  ErrorBanner,
  fmtUsd,
  fmtPct,
  fmtNum,
  fmtSignedUsd,
  fmtSignedPct,
} from "../components/ui";
import { RegimeBanner } from "../components/RegimeBanner";
import { SectionGuide } from "../components/SectionGuide";

const finiteNumber = (n: number | string | null | undefined): number | null => {
  if (n == null || n === "") return null;
  const value = typeof n === "number" ? n : Number(n);
  return Number.isFinite(value) ? value : null;
};

const numeric = (n: number | string | null | undefined) => finiteNumber(n) ?? 0;

const signClass = (n: number | string | null | undefined) => {
  const value = finiteNumber(n);
  return value == null || value === 0 ? "text-slate-200" : value > 0 ? "text-buy" : "text-sell";
};

const parseBrokerDate = (d: string | null | undefined) => {
  if (!d) return null;
  const hasZone = /(?:z|[+-]\d{2}:?\d{2})$/i.test(d);
  const date = new Date(hasZone ? d : `${d}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
};

const fmtDateTime = (d: string | null | undefined) => {
  const date = parseBrokerDate(d);
  return date == null
    ? "—"
    : date.toLocaleString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
        timeZone: "Asia/Singapore",
        timeZoneName: "short",
      });
};

function orderStatusClass(s: string | null | undefined): string {
  const st = (s ?? "").toLowerCase();
  if (st === "filled") return "bg-buy/15 text-buy border-buy/40";
  if (["canceled", "cancelled", "rejected", "expired"].includes(st))
    return "bg-sell/15 text-sell border-sell/40";
  return "bg-hold/15 text-slate-300 border-hold/40";
}

const fmtOrderPrice = (n: number | null | undefined) =>
  n == null || !Number.isFinite(n) || Math.abs(n) > 1e20 ? "-" : fmtUsd(n);

function DefRow({ label, value, tone }: { label: string; value: ReactNode; tone?: string }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5 border-b border-edge/60 last:border-0">
      <span className="text-xs text-slate-400">{label}</span>
      <span className={`text-sm font-medium tabular-nums ${tone ?? "text-slate-100"}`}>{value}</span>
    </div>
  );
}

export function Dashboard() {
  const qc = useQueryClient();
  const [confirmSell, setConfirmSell] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const portfolio = useQuery({
    queryKey: ["portfolio"],
    queryFn: api.portfolio,
    refetchInterval: 10_000,
  });
  const reco = useQuery({
    queryKey: ["reco"],
    queryFn: () => api.recommendations(false),
    refetchInterval: 30_000,
  });
  const configured = portfolio.data?.configured ?? false;
  const orders = useQuery({
    queryKey: ["orders", "open"],
    // IBKR PendingSubmit orders are present in the session trade list but can be
    // absent from reqOpenOrders() until fully transmitted. Request all current
    // session trades so the dashboard still shows pending paper exits.
    queryFn: () => api.orders("all"),
    refetchInterval: 10_000,
    enabled: configured,
  });
  const activities = useQuery({
    queryKey: ["activities"],
    queryFn: () => api.activities(50),
    refetchInterval: 30_000,
    enabled: configured,
  });

  const refreshAll = async () => {
    setRefreshing(true);
    try {
      await Promise.all([
        qc.refetchQueries({ queryKey: ["portfolio"], exact: true }),
        qc.refetchQueries({ queryKey: ["orders", "open"], exact: true }),
        qc.refetchQueries({ queryKey: ["activities"], exact: true }),
        qc.refetchQueries({ queryKey: ["reco"], exact: true }),
      ]);
    } finally {
      setRefreshing(false);
    }
  };

  const sell = useMutation({
    mutationFn: (v: { symbol: string }) => api.closePosition(v.symbol),
    onSuccess: () => {
      setConfirmSell(null);
      refreshAll();
    },
  });
  const cancel = useMutation({
    mutationFn: (id: string) => api.cancelOrder(id),
    // Broker cancellation can be async — the order may remain pending briefly.
    // Drop it from the cache right away for instant feedback; the 10s poll reconciles after.
    onSuccess: (_data, id) => {
      qc.setQueryData<{ orders: OrderRow[] }>(["orders", "open"], (prev) =>
        prev ? { orders: prev.orders.filter((o) => o.id !== id) } : prev,
      );
      qc.invalidateQueries({ queryKey: ["portfolio"] });
    },
  });

  if (portfolio.isLoading) return <Spinner label="Loading portfolio…" />;
  if (portfolio.isError) return <ErrorBanner message={(portfolio.error as Error).message} />;
  const p = portfolio.data;

  if (p && !p.configured) {
    return (
      <ErrorBanner
        message={p.message ?? "IBKR is not configured or not connected. Start TWS/Gateway and check backend/.env."}
      />
    );
  }

  const acct: Account | null | undefined = p?.account;
  const positions: Position[] = p?.positions ?? [];
  const openOrders: OrderRow[] = orders.data?.orders ?? [];
  const acts: Activity[] = activities.data?.activities ?? [];

  const dayPl = acct ? numeric(acct.equity) - numeric(acct.last_equity) : 0;
  const dayPlPct = acct && numeric(acct.last_equity) ? dayPl / numeric(acct.last_equity) : 0;

  const totals = positions.reduce(
    (a, pos) => ({
      mv: a.mv + numeric(pos.market_value),
      cost: a.cost + numeric(pos.cost_basis),
      pl: a.pl + numeric(pos.unrealized_pl),
      day: a.day + numeric(pos.unrealized_intraday_pl),
    }),
    { mv: 0, cost: 0, pl: 0, day: 0 },
  );
  const totalPlPct = totals.cost ? totals.pl / totals.cost : 0;
  const updatedAt = portfolio.dataUpdatedAt ? new Date(portfolio.dataUpdatedAt) : null;

  return (
    <div className="space-y-5">
      <RegimeBanner regime={reco.data?.regime} />
      <SectionGuide id="dashboard" />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-bold text-slate-100">Account Overview</h2>
          <span
            className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded border ${
              acct?.is_paper
                ? "bg-accent/15 text-accent border-accent/40"
                : "bg-sell/15 text-sell border-sell/40"
            }`}
          >
            {acct?.is_paper ? "Paper" : "Live"}
          </span>
          {acct?.status && (
            <span className="text-[10px] uppercase tracking-wide text-slate-500">{acct.status}</span>
          )}
        </div>
        <div className="flex items-center gap-3 text-xs text-slate-500">
          {updatedAt && <span>Updated {updatedAt.toLocaleTimeString()}</span>}
          <button
            onClick={refreshAll}
            disabled={refreshing}
            className="px-3 py-1.5 rounded-lg border bg-panel2 border-edge text-slate-300 hover:bg-edge"
          >
            {refreshing ? "Refreshing…" : "↻ Refresh"}
          </button>
        </div>
      </div>

      {/* ── Balances summary ─────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat
          label="Portfolio Value"
          value={fmtUsd(acct?.portfolio_value)}
          sub={`${fmtSignedUsd(dayPl)} (${fmtSignedPct(dayPlPct)}) today`}
          tone={dayPl > 0 ? "up" : dayPl < 0 ? "down" : "neutral"}
        />
        <Stat label="Equity" value={fmtUsd(acct?.equity)} sub={`Prev close ${fmtUsd(acct?.last_equity)}`} />
        <Stat
          label="Cash"
          value={fmtUsd(acct?.cash)}
          sub={`${fmtPct(acct?.equity ? (numeric(acct.cash) / numeric(acct.equity)) : 0)} of equity`}
        />
        <Stat
          label="Buying Power"
          value={fmtUsd(acct?.buying_power)}
          sub={`RegT ${fmtUsd(acct?.regt_buying_power)}`}
        />
      </div>

      {sell.isError && <ErrorBanner message={(sell.error as Error).message} />}
      {cancel.isError && <ErrorBanner message={(cancel.error as Error).message} />}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <Panel title="Balances" className="lg:col-span-2">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8">
            <div>
              <DefRow label="Long market value" value={fmtUsd(acct?.long_market_value)} />
              <DefRow label="Short market value" value={fmtUsd(acct?.short_market_value)} />
              <DefRow label="Position market value" value={fmtUsd(acct?.position_market_value)} />
              <DefRow label="Cash" value={fmtUsd(acct?.cash)} />
              <DefRow label="Accrued fees" value={fmtUsd(acct?.accrued_fees)} />
              <DefRow label="Account number" value={acct?.account_number || "—"} />
            </div>
            <div>
              <DefRow label="Initial margin" value={fmtUsd(acct?.initial_margin)} />
              <DefRow label="Maintenance margin" value={fmtUsd(acct?.maintenance_margin)} />
              <DefRow label="Day-trading buying power" value={fmtUsd(acct?.daytrading_buying_power)} />
              <DefRow
                label="Day trades (5d)"
                value={String(acct?.daytrade_count ?? 0)}
                tone={(acct?.daytrade_count ?? 0) >= 3 ? "text-hold" : undefined}
              />
              <DefRow
                label="Pattern day trader"
                value={acct?.pattern_day_trader ? "Yes" : "No"}
                tone={acct?.pattern_day_trader ? "text-hold" : undefined}
              />
              <DefRow
                label="Trading status"
                value={acct?.trading_blocked ? "Blocked" : "Active"}
                tone={acct?.trading_blocked ? "text-sell" : "text-buy"}
              />
            </div>
          </div>
        </Panel>

        <Panel
          title="Top Signals"
          right={<Link to="/recommendations" className="text-xs text-accent">View all →</Link>}
        >
          {reco.isLoading ? (
            <Spinner />
          ) : (
            <div className="space-y-2">
              {(reco.data?.top_buys ?? []).slice(0, 5).map((r) => (
                <Link
                  to={`/ticker/${r.symbol}`}
                  key={r.symbol}
                  className="flex items-center justify-between bg-panel2 rounded-lg px-3 py-2 hover:bg-edge"
                >
                  <span className="font-semibold">{r.symbol}</span>
                  <span className="text-buy text-sm">+{r.score.toFixed(2)}</span>
                </Link>
              ))}
              {(reco.data?.top_buys ?? []).length === 0 && (
                <p className="text-slate-400 text-sm py-4 text-center">No buy signals right now.</p>
              )}
            </div>
          )}
        </Panel>
      </div>

      {/* ── Positions ────────────────────────────────────────────────── */}
      <Panel title={`Positions${positions.length ? ` (${positions.length})` : ""}`}>
        {positions.length === 0 ? (
          <p className="text-slate-400 text-sm py-6 text-center">No open positions.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm whitespace-nowrap">
              <thead className="text-slate-400 text-xs uppercase">
                <tr className="text-left">
                  <th className="py-2 pr-3">Symbol</th>
                  <th className="pr-3">Side</th>
                  <th className="pr-3 text-right">Qty</th>
                  <th className="pr-3 text-right">Avg Entry</th>
                  <th className="pr-3 text-right">Last</th>
                  <th className="pr-3 text-right">Cost Basis</th>
                  <th className="pr-3 text-right">Mkt Value</th>
                  <th className="pr-3 text-right">Today</th>
                  <th className="pr-3 text-right">Total P/L</th>
                  <th className="text-right">Close</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos) => {
                  const selling = sell.isPending && sell.variables?.symbol === pos.symbol;
                  const armed = confirmSell === pos.symbol;
                  return (
                    <tr key={pos.symbol} className="border-t border-edge">
                      <td className="py-2 pr-3 font-semibold">
                        <Link to={`/ticker/${pos.symbol}`} className="hover:text-accent">
                          {pos.symbol}
                        </Link>
                      </td>
                      <td className="pr-3">
                        <span className={pos.side === "long" ? "text-buy" : "text-sell"}>
                          {pos.side}
                        </span>
                      </td>
                      <td className="pr-3 text-right tabular-nums">{fmtNum(pos.qty, 0)}</td>
                      <td className="pr-3 text-right tabular-nums">{fmtUsd(pos.avg_entry_price)}</td>
                      <td className="pr-3 text-right tabular-nums">{fmtUsd(pos.current_price)}</td>
                      <td className="pr-3 text-right tabular-nums text-slate-400">
                        {fmtUsd(pos.cost_basis)}
                      </td>
                      <td className="pr-3 text-right tabular-nums">{fmtUsd(pos.market_value)}</td>
                      <td className={`pr-3 text-right tabular-nums ${signClass(pos.unrealized_intraday_pl)}`}>
                        {fmtSignedUsd(pos.unrealized_intraday_pl)}
                        <span className="block text-[11px] opacity-80">
                          {fmtSignedPct(pos.change_today)}
                        </span>
                      </td>
                      <td className={`pr-3 text-right tabular-nums ${signClass(pos.unrealized_pl)}`}>
                        {fmtSignedUsd(pos.unrealized_pl)}
                        <span className="block text-[11px] opacity-80">
                          {fmtSignedPct(pos.unrealized_plpc)}
                        </span>
                      </td>
                      <td className="text-right">
                        <button
                          onClick={() =>
                            armed ? sell.mutate({ symbol: pos.symbol }) : setConfirmSell(pos.symbol)
                          }
                          onBlur={() => armed && setConfirmSell(null)}
                          disabled={selling}
                          className={`text-xs px-2.5 py-1 rounded-lg border disabled:opacity-40 ${
                            armed
                              ? "bg-sell/30 border-sell/60 text-sell"
                              : "bg-sell/10 border-sell/40 text-sell hover:bg-sell/20"
                          }`}
                          title={`Close all ${fmtNum(pos.qty, 0)} ${pos.symbol} at market`}
                        >
                          {selling ? "…" : armed ? "Confirm" : "Close"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-edge text-xs">
                  <td className="py-2 pr-3 font-semibold text-slate-300" colSpan={5}>
                    Total
                  </td>
                  <td className="pr-3 text-right tabular-nums text-slate-400">{fmtUsd(totals.cost)}</td>
                  <td className="pr-3 text-right tabular-nums text-slate-200">{fmtUsd(totals.mv)}</td>
                  <td className={`pr-3 text-right tabular-nums ${signClass(totals.day)}`}>
                    {fmtSignedUsd(totals.day)}
                  </td>
                  <td className={`pr-3 text-right tabular-nums ${signClass(totals.pl)}`}>
                    {fmtSignedUsd(totals.pl)} ({fmtSignedPct(totalPlPct)})
                  </td>
                  <td />
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </Panel>

      {/* ── Open orders ──────────────────────────────────────────────── */}
      <Panel title={`Open Orders${openOrders.length ? ` (${openOrders.length})` : ""}`}>
        {openOrders.length === 0 ? (
          <p className="text-slate-400 text-sm py-4 text-center">No working orders.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm whitespace-nowrap">
              <thead className="text-slate-400 text-xs uppercase">
                <tr className="text-left">
                  <th className="py-2 pr-3">Submitted</th>
                  <th className="pr-3">Symbol</th>
                  <th className="pr-3">Side</th>
                  <th className="pr-3 text-right">Qty</th>
                  <th className="pr-3 text-right">Filled</th>
                  <th className="pr-3">Type</th>
                  <th className="pr-3 text-right">Limit</th>
                  <th className="pr-3 text-right">Stop</th>
                  <th className="pr-3">TIF</th>
                  <th className="pr-3">Status</th>
                  <th className="text-right">Cancel</th>
                </tr>
              </thead>
              <tbody>
                {openOrders.map((o) => (
                  <tr key={o.id} className="border-t border-edge">
                    <td className="py-2 pr-3 text-slate-400">{fmtDateTime(o.submitted_at)}</td>
                    <td className="pr-3 font-semibold">
                      <Link to={`/ticker/${o.symbol}`} className="hover:text-accent">
                        {o.symbol}
                      </Link>
                    </td>
                    <td className={`pr-3 ${o.side === "buy" ? "text-buy" : "text-sell"}`}>{o.side}</td>
                    <td className="pr-3 text-right tabular-nums">{fmtNum(o.qty, 0)}</td>
                    <td className="pr-3 text-right tabular-nums text-slate-400">{fmtNum(o.filled_qty, 0)}</td>
                    <td className="pr-3 text-slate-300">
                      {o.type}
                      {o.order_class && o.order_class !== "simple" && (
                        <span className="text-slate-500"> · {o.order_class}</span>
                      )}
                    </td>
                    <td className="pr-3 text-right tabular-nums text-slate-300">
                      {fmtOrderPrice(o.limit_price)}
                    </td>
                    <td className="pr-3 text-right tabular-nums text-slate-300">
                      {fmtOrderPrice(o.stop_price)}
                    </td>
                    <td className="pr-3 uppercase text-slate-400">{o.time_in_force || "—"}</td>
                    <td className="pr-3">
                      <span
                        className={`text-[11px] px-1.5 py-0.5 rounded border ${orderStatusClass(o.status)}`}
                      >
                        {o.status}
                      </span>
                    </td>
                    <td className="text-right">
                      <button
                        onClick={() => cancel.mutate(o.id)}
                        disabled={cancel.isPending && cancel.variables === o.id}
                        className="text-xs px-2.5 py-1 rounded-lg border bg-panel2 border-edge text-slate-300 hover:bg-edge disabled:opacity-40"
                      >
                        {cancel.isPending && cancel.variables === o.id ? "…" : "Cancel"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {/* ── Account activities ───────────────────────────────────────── */}
      <Panel
        title="Activity"
        right={<Link to="/history" className="text-xs text-accent">Full history →</Link>}
      >
        {activities.isLoading ? (
          <Spinner />
        ) : acts.length === 0 ? (
          <p className="text-slate-400 text-sm py-4 text-center">No account activity yet.</p>
        ) : (
          <div className="max-h-[26rem] overflow-auto">
            <table className="w-full text-sm whitespace-nowrap">
              <thead className="text-slate-400 text-xs uppercase sticky top-0 bg-panel">
                <tr className="text-left">
                  <th className="py-2 pr-3">Date</th>
                  <th className="pr-3">Type</th>
                  <th className="pr-3">Symbol</th>
                  <th className="pr-3">Side</th>
                  <th className="pr-3 text-right">Qty</th>
                  <th className="pr-3 text-right">Price</th>
                  <th className="text-right">Net Amount</th>
                </tr>
              </thead>
              <tbody>
                {acts.map((a) => (
                  <tr key={a.id} className="border-t border-edge">
                    <td className="py-1.5 pr-3 text-slate-400">{fmtDateTime(a.date)}</td>
                    <td className="pr-3 text-slate-300">{a.activity_type}</td>
                    <td className="pr-3 font-semibold">
                      {a.symbol ? (
                        <Link to={`/ticker/${a.symbol}`} className="hover:text-accent">
                          {a.symbol}
                        </Link>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className={`pr-3 ${a.side === "buy" ? "text-buy" : a.side === "sell" ? "text-sell" : "text-slate-400"}`}>
                      {a.side || "—"}
                    </td>
                    <td className="pr-3 text-right tabular-nums">{a.qty ? fmtNum(a.qty, 0) : "—"}</td>
                    <td className="pr-3 text-right tabular-nums">{a.price ? fmtUsd(a.price) : "—"}</td>
                    <td className={`text-right tabular-nums ${signClass(a.net_amount)}`}>
                      {a.net_amount ? fmtSignedUsd(a.net_amount) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <p className="text-[11px] text-slate-500">
        Positions, orders, balances and activity are read live from your IBKR
        {acct?.is_paper ? " paper" : ""} session via TWS/Gateway.
      </p>
    </div>
  );
}
