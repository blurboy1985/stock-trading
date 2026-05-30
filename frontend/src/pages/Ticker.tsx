import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { PriceChart } from "../components/PriceChart";
import { Panel, Spinner, ErrorBanner, fmtUsd, fmtPct } from "../components/ui";

type RangeKey = "1M" | "3M" | "YTD" | "1Y" | "3Y" | "5Y" | "ALL";

// Calendar-day lookback for each range (YTD is computed from Jan 1).
function rangeDays(key: RangeKey): number {
  const now = new Date();
  switch (key) {
    case "1M":
      return 31;
    case "3M":
      return 93;
    case "YTD":
      return Math.max(
        1,
        Math.ceil(
          (now.getTime() - new Date(now.getFullYear(), 0, 1).getTime()) / 86_400_000,
        ),
      );
    case "1Y":
      return 365;
    case "3Y":
      return 365 * 3;
    case "5Y":
      return 365 * 5;
    case "ALL":
      return 8000;
  }
}

const RANGES: RangeKey[] = ["1M", "3M", "YTD", "1Y", "3Y", "5Y", "ALL"];

export function Ticker() {
  const { symbol = "" } = useParams();
  const qc = useQueryClient();
  const [qty, setQty] = useState("");
  const [range, setRange] = useState<RangeKey>("1Y");

  const days = rangeDays(range);
  const bars = useQuery({
    queryKey: ["bars", symbol, range],
    queryFn: () => api.bars(symbol, days),
  });
  const quote = useQuery({
    queryKey: ["quote", symbol],
    queryFn: () => api.quote(symbol),
    refetchInterval: 10_000,
  });
  const asset = useQuery({
    queryKey: ["asset", symbol],
    queryFn: () => api.asset(symbol),
    staleTime: 24 * 60 * 60 * 1000,
    retry: false,
  });
  const news = useQuery({ queryKey: ["news", symbol], queryFn: () => api.news(symbol) });

  // Period return over whatever the chart is currently showing.
  const seriesBars = bars.data?.bars ?? [];
  const periodChange =
    seriesBars.length > 1
      ? seriesBars[seriesBars.length - 1].close / seriesBars[0].close - 1
      : null;

  const order = useMutation({
    mutationFn: (side: string) =>
      api.placeOrder({ symbol, side, qty: qty ? Number(qty) : null }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["portfolio"] }),
  });

  return (
    <div className="space-y-5">
      <div className="flex items-baseline gap-3 flex-wrap">
        <h2 className="text-3xl font-bold">{symbol}</h2>
        {asset.data?.name && (
          <span className="text-lg text-slate-400 font-medium">{asset.data.name}</span>
        )}
        {asset.data?.exchange && (
          <span className="text-xs text-slate-500 border border-edge rounded px-1.5 py-0.5">
            {asset.data.exchange}
          </span>
        )}
        {quote.data && (
          <span className="text-xl text-slate-700 font-semibold ml-auto">
            {fmtUsd(quote.data.mid)}
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <Panel className="lg:col-span-2 !p-0 overflow-hidden">
          <div className="flex items-center justify-between gap-3 flex-wrap px-5 pt-4">
            <div className="flex items-baseline gap-2">
              <h3 className="text-[11px] font-bold text-slate-400 uppercase tracking-[0.1em]">
                Price · {range}
              </h3>
              {periodChange != null && (
                <span
                  className={`text-xs font-semibold ${
                    periodChange >= 0 ? "text-buy" : "text-sell"
                  }`}
                >
                  {periodChange >= 0 ? "+" : ""}
                  {fmtPct(periodChange, 1)}
                </span>
              )}
            </div>
            <div className="flex gap-1">
              {RANGES.map((r) => (
                <button
                  key={r}
                  onClick={() => setRange(r)}
                  className={`text-xs font-medium px-2.5 py-1 rounded-md border transition-colors ${
                    range === r
                      ? "bg-accent/15 border-accent/40 text-accent"
                      : "bg-panel border-edge text-slate-400 hover:bg-panel2"
                  }`}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>
          <div className="px-2 pb-2 pt-1">
            {bars.isLoading ? (
              <Spinner />
            ) : bars.isError ? (
              <ErrorBanner message={(bars.error as Error).message} />
            ) : (
              <PriceChart
                bars={bars.data!.bars}
                variant={days > 370 ? "area" : "candles"}
              />
            )}
          </div>
        </Panel>

        <Panel title="Trade (paper)">
          <div className="space-y-3">
            <input
              type="number"
              placeholder="Qty (blank = auto-size)"
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              className="w-full bg-panel2 border border-edge rounded-lg px-3 py-2 text-sm"
            />
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => order.mutate("buy")}
                disabled={order.isPending}
                className="bg-buy/20 border border-buy/40 text-buy py-2 rounded-lg hover:bg-buy/30 disabled:opacity-50"
              >
                Buy
              </button>
              <button
                onClick={() => order.mutate("sell")}
                disabled={order.isPending}
                className="bg-sell/20 border border-sell/40 text-sell py-2 rounded-lg hover:bg-sell/30 disabled:opacity-50"
              >
                Sell
              </button>
            </div>
            {order.isError && <ErrorBanner message={(order.error as Error).message} />}
            {order.isSuccess && (
              <div className="text-buy text-sm">Order submitted ✓</div>
            )}
            <p className="text-xs text-slate-500">
              Orders are risk-checked (position size, exposure, stop-loss/take-profit)
              before submission.
            </p>
          </div>
        </Panel>
      </div>

      <Panel title="Recent News">
        {news.isLoading ? (
          <Spinner />
        ) : (news.data?.news ?? []).length === 0 ? (
          <p className="text-slate-400 text-sm py-4">No recent news.</p>
        ) : (
          <ul className="space-y-2">
            {news.data!.news.slice(0, 10).map((n: any, i: number) => (
              <li key={i} className="text-sm border-b border-edge pb-2">
                <a href={n.url} target="_blank" rel="noreferrer" className="hover:text-accent">
                  {n.headline}
                </a>
                <span className="text-slate-500 text-xs ml-2">{n.source}</span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
