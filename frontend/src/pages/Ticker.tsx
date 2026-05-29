import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { PriceChart } from "../components/PriceChart";
import { Panel, Spinner, ErrorBanner, fmtUsd } from "../components/ui";

export function Ticker() {
  const { symbol = "" } = useParams();
  const qc = useQueryClient();
  const [qty, setQty] = useState("");

  const bars = useQuery({
    queryKey: ["bars", symbol],
    queryFn: () => api.bars(symbol, 250),
  });
  const quote = useQuery({
    queryKey: ["quote", symbol],
    queryFn: () => api.quote(symbol),
    refetchInterval: 10_000,
  });
  const news = useQuery({ queryKey: ["news", symbol], queryFn: () => api.news(symbol) });

  const order = useMutation({
    mutationFn: (side: string) =>
      api.placeOrder({ symbol, side, qty: qty ? Number(qty) : null }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["portfolio"] }),
  });

  return (
    <div className="space-y-5">
      <div className="flex items-baseline gap-4">
        <h2 className="text-3xl font-bold">{symbol}</h2>
        {quote.data && (
          <span className="text-xl text-slate-300">{fmtUsd(quote.data.mid)}</span>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <Panel title="Price (250d)" className="lg:col-span-2">
          {bars.isLoading ? (
            <Spinner />
          ) : bars.isError ? (
            <ErrorBanner message={(bars.error as Error).message} />
          ) : (
            <PriceChart bars={bars.data!.bars} />
          )}
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
