import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type Recommendation } from "../api/client";
import {
  Panel,
  Spinner,
  ErrorBanner,
  ActionBadge,
  ScoreBar,
  fmtUsd,
} from "../components/ui";

export function Recommendations() {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState<string | null>(null);

  const reco = useQuery({
    queryKey: ["reco"],
    queryFn: () => api.recommendations(false),
    refetchInterval: 30_000,
  });

  const refresh = useMutation({
    mutationFn: () => api.recommendations(true),
    onSuccess: (d) => qc.setQueryData(["reco"], d),
  });

  const buy = useMutation({
    mutationFn: (symbol: string) => api.placeOrder({ symbol, side: "buy" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["portfolio"] }),
  });

  if (reco.isLoading) return <Spinner label="Scoring the universe…" />;
  const data = reco.data;
  const recs = data?.recommendations ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-sm text-slate-400">
          {data?.generated_at
            ? `Updated ${new Date(data.generated_at).toLocaleTimeString()}`
            : "Not yet generated"}
        </div>
        <button
          onClick={() => refresh.mutate()}
          disabled={refresh.isPending}
          className="bg-accent/20 border border-accent/40 text-accent text-sm px-3 py-1.5 rounded-lg hover:bg-accent/30 disabled:opacity-50"
        >
          {refresh.isPending ? "Refreshing…" : "Refresh now"}
        </button>
      </div>

      {buy.isError && <ErrorBanner message={(buy.error as Error).message} />}
      {recs.length === 0 && (
        <ErrorBanner message="No recommendations. Configure Alpaca credentials and refresh." />
      )}

      <div className="space-y-2">
        {recs.map((r) => (
          <RecoRow
            key={r.symbol}
            r={r}
            expanded={expanded === r.symbol}
            onToggle={() => setExpanded(expanded === r.symbol ? null : r.symbol)}
            onBuy={() => buy.mutate(r.symbol)}
            buying={buy.isPending && buy.variables === r.symbol}
          />
        ))}
      </div>
    </div>
  );
}

function RecoRow({
  r,
  expanded,
  onToggle,
  onBuy,
  buying,
}: {
  r: Recommendation;
  expanded: boolean;
  onToggle: () => void;
  onBuy: () => void;
  buying: boolean;
}) {
  return (
    <Panel className="!p-0 overflow-hidden">
      <div className="flex items-center gap-4 px-4 py-3">
        <div className="w-20">
          <Link to={`/ticker/${r.symbol}`} className="font-bold text-lg hover:text-accent">
            {r.symbol}
          </Link>
        </div>
        <ActionBadge action={r.action} />
        <div className="flex-1 max-w-xs">
          <ScoreBar score={r.score} />
        </div>
        <div className="w-16 text-right font-mono text-sm">
          {r.score >= 0 ? "+" : ""}
          {r.score.toFixed(2)}
        </div>
        <div className="w-20 text-right text-sm text-slate-300">{fmtUsd(r.price)}</div>
        <button
          onClick={onBuy}
          disabled={buying || r.action === "SELL"}
          className="bg-buy/20 border border-buy/40 text-buy text-xs px-3 py-1.5 rounded-lg hover:bg-buy/30 disabled:opacity-30"
        >
          {buying ? "…" : "Buy"}
        </button>
        <button onClick={onToggle} className="text-slate-400 text-xs w-6">
          {expanded ? "▲" : "▼"}
        </button>
      </div>
      {expanded && (
        <div className="bg-panel2 px-4 py-3 border-t border-edge">
          <div className="text-xs text-slate-400 mb-2">Why this score:</div>
          <ul className="text-sm text-slate-200 list-disc pl-5 space-y-0.5 mb-3">
            {r.reasons.map((reason, i) => (
              <li key={i}>{reason}</li>
            ))}
          </ul>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {Object.entries(r.breakdown).map(([name, b]) => (
              <div key={name} className="bg-panel rounded-lg px-3 py-2">
                <div className="text-xs text-slate-400 capitalize">{name}</div>
                <div
                  className={`font-mono text-sm ${
                    b.score > 0 ? "text-buy" : b.score < 0 ? "text-sell" : "text-slate-300"
                  }`}
                >
                  {b.score >= 0 ? "+" : ""}
                  {b.score.toFixed(2)}
                  <span className="text-slate-500 text-xs"> ·w{b.weight.toFixed(2)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </Panel>
  );
}
