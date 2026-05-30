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
  fmtPct,
} from "../components/ui";
import { RegimeBanner } from "../components/RegimeBanner";

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
      <RegimeBanner regime={data?.regime} />
      <div className="flex items-center justify-between">
        <div className="text-sm text-slate-400">
          {data?.generated_at
            ? `Ranked by risk-adjusted score · updated ${new Date(
                data.generated_at,
              ).toLocaleTimeString()}`
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
          {r.liquidity_warning && (
            <div className="text-[10px] text-sell" title={r.liquidity_warning}>
              ⚠ thin
            </div>
          )}
        </div>
        <ActionBadge action={r.action} />
        <div className="flex-1 max-w-[10rem]">
          <ScoreBar score={r.score} />
        </div>
        <Metric label="score" className="w-14">
          <span className="font-mono">
            {r.score >= 0 ? "+" : ""}
            {r.score.toFixed(2)}
          </span>
        </Metric>
        <Metric label="conv" className="w-12">
          <span className="font-mono text-slate-200">
            {r.conviction != null ? r.conviction.toFixed(2) : "—"}
          </span>
        </Metric>
        <Metric label="vol" className="w-12">
          <span className="font-mono text-slate-400">
            {r.atr_pct != null ? fmtPct(r.atr_pct, 1) : "—"}
          </span>
        </Metric>
        <Metric label="size" className="w-14">
          <span className="font-mono text-slate-300">
            {r.suggested_weight_pct != null ? fmtPct(r.suggested_weight_pct, 1) : "—"}
          </span>
        </Metric>
        <div className="w-16 text-right text-sm text-slate-300">{fmtUsd(r.price)}</div>
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
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-300 mb-3">
            <span>
              Rank score{" "}
              <span className="font-mono text-slate-100">
                {r.rank_score != null ? r.rank_score.toFixed(3) : "—"}
              </span>
            </span>
            <span>
              Agreement{" "}
              <span className="font-mono text-slate-100">
                {r.agreement != null ? fmtPct(r.agreement, 0) : "—"}
              </span>
            </span>
            <span>
              Suggested size{" "}
              <span className="font-mono text-slate-100">
                {r.suggested_weight_pct != null ? fmtPct(r.suggested_weight_pct, 1) : "—"}
                {r.suggested_qty != null ? ` · ${r.suggested_qty} sh` : ""}
              </span>
            </span>
            {r.regime_multiplier != null && r.regime_multiplier < 1 && (
              <span className="text-sell">
                regime dampened ×{r.regime_multiplier.toFixed(2)}
              </span>
            )}
          </div>
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

function Metric({
  label,
  children,
  className = "",
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`text-right ${className}`}>
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className="text-sm leading-tight">{children}</div>
    </div>
  );
}
