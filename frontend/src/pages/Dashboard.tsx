import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { Panel, Stat, Spinner, ErrorBanner, fmtUsd, fmtPct } from "../components/ui";
import { RegimeBanner } from "../components/RegimeBanner";

export function Dashboard() {
  const qc = useQueryClient();
  const [confirmSell, setConfirmSell] = useState<string | null>(null);

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
    queryFn: () => api.orders("open"),
    refetchInterval: 10_000,
    enabled: configured,
  });

  const refreshBook = () => {
    qc.invalidateQueries({ queryKey: ["portfolio"] });
    qc.invalidateQueries({ queryKey: ["orders", "open"] });
  };

  const sell = useMutation({
    mutationFn: (v: { symbol: string; qty: number }) =>
      api.placeOrder({ symbol: v.symbol, side: "sell", qty: v.qty }),
    onSuccess: () => {
      setConfirmSell(null);
      refreshBook();
    },
  });
  const cancel = useMutation({
    mutationFn: (id: string) => api.cancelOrder(id),
    onSuccess: refreshBook,
  });

  if (portfolio.isLoading) return <Spinner label="Loading portfolio…" />;
  const p = portfolio.data;

  if (p && !p.configured) {
    return (
      <ErrorBanner
        message={p.message ?? "Alpaca credentials are not configured. Add them in backend/.env."}
      />
    );
  }

  const acct = p?.account;
  const dayPl = acct ? acct.equity - acct.last_equity : 0;
  const dayPlPct = acct && acct.last_equity ? dayPl / acct.last_equity : 0;
  const positions = p?.positions ?? [];
  const openOrders = orders.data?.orders ?? [];

  return (
    <div className="space-y-5">
      <RegimeBanner regime={reco.data?.regime} />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Equity" value={fmtUsd(acct?.equity)} />
        <Stat
          label="Today's P&L"
          value={fmtUsd(dayPl)}
          sub={fmtPct(dayPlPct)}
          tone={dayPl >= 0 ? "up" : "down"}
        />
        <Stat label="Cash" value={fmtUsd(acct?.cash)} />
        <Stat label="Buying Power" value={fmtUsd(acct?.buying_power)} />
      </div>

      {sell.isError && <ErrorBanner message={(sell.error as Error).message} />}
      {cancel.isError && <ErrorBanner message={(cancel.error as Error).message} />}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <Panel title="Open Positions" className="lg:col-span-2">
          {positions.length === 0 ? (
            <p className="text-slate-400 text-sm py-6 text-center">No open positions.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-slate-400 text-xs uppercase">
                <tr className="text-left">
                  <th className="py-2">Symbol</th>
                  <th>Qty</th>
                  <th>Avg</th>
                  <th>Last</th>
                  <th>Value</th>
                  <th className="text-right">Unrealized P&L</th>
                  <th className="text-right">Close</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos) => {
                  const selling = sell.isPending && sell.variables?.symbol === pos.symbol;
                  const armed = confirmSell === pos.symbol;
                  return (
                    <tr key={pos.symbol} className="border-t border-edge">
                      <td className="py-2 font-semibold">
                        <Link to={`/ticker/${pos.symbol}`} className="hover:text-accent">
                          {pos.symbol}
                        </Link>
                      </td>
                      <td>{pos.qty}</td>
                      <td>{fmtUsd(pos.avg_entry_price)}</td>
                      <td>{fmtUsd(pos.current_price)}</td>
                      <td>{fmtUsd(pos.market_value)}</td>
                      <td
                        className={`text-right font-medium ${
                          pos.unrealized_pl >= 0 ? "text-buy" : "text-sell"
                        }`}
                      >
                        {fmtUsd(pos.unrealized_pl)} ({fmtPct(pos.unrealized_plpc)})
                      </td>
                      <td className="text-right">
                        <button
                          onClick={() =>
                            armed
                              ? sell.mutate({ symbol: pos.symbol, qty: pos.qty })
                              : setConfirmSell(pos.symbol)
                          }
                          onBlur={() => armed && setConfirmSell(null)}
                          disabled={selling}
                          className={`text-xs px-2.5 py-1 rounded-lg border disabled:opacity-40 ${
                            armed
                              ? "bg-sell/30 border-sell/60 text-sell"
                              : "bg-sell/10 border-sell/40 text-sell hover:bg-sell/20"
                          }`}
                          title={`Sell all ${pos.qty} ${pos.symbol} at market (paper)`}
                        >
                          {selling ? "…" : armed ? "Confirm" : "Sell"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </Panel>

        <Panel title="Top Signals" right={<Link to="/recommendations" className="text-xs text-accent">View all →</Link>}>
          {reco.isLoading ? (
            <Spinner />
          ) : (
            <div className="space-y-2">
              {(reco.data?.top_buys ?? []).slice(0, 4).map((r) => (
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
                <p className="text-slate-400 text-sm py-4 text-center">
                  No buy signals right now.
                </p>
              )}
            </div>
          )}
        </Panel>
      </div>

      <Panel title="Open Orders">
        {openOrders.length === 0 ? (
          <p className="text-slate-400 text-sm py-4 text-center">
            No working orders.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-slate-400 text-xs uppercase">
              <tr className="text-left">
                <th className="py-2">Symbol</th>
                <th>Side</th>
                <th>Qty</th>
                <th>Filled</th>
                <th>Type</th>
                <th>Status</th>
                <th className="text-right">Cancel</th>
              </tr>
            </thead>
            <tbody>
              {openOrders.map((o: any) => (
                <tr key={o.id} className="border-t border-edge">
                  <td className="py-2 font-semibold">
                    <Link to={`/ticker/${o.symbol}`} className="hover:text-accent">
                      {o.symbol}
                    </Link>
                  </td>
                  <td className={o.side === "buy" ? "text-buy" : "text-sell"}>{o.side}</td>
                  <td>{o.qty}</td>
                  <td className="text-slate-400">{o.filled_qty ?? 0}</td>
                  <td className="text-slate-400">{o.type}</td>
                  <td className="text-slate-400">{o.status}</td>
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
        )}
      </Panel>
    </div>
  );
}
