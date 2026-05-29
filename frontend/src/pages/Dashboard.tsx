import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { Panel, Stat, Spinner, ErrorBanner, fmtUsd, fmtPct } from "../components/ui";

export function Dashboard() {
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

  return (
    <div className="space-y-5">
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
                </tr>
              </thead>
              <tbody>
                {positions.map((pos) => (
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
                  </tr>
                ))}
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
    </div>
  );
}
