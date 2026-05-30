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

// Sizing/threshold context pulled from Settings so the explanations below show
// the user's *actual* knobs rather than hard-coded defaults.
interface SizingCfg {
  buyThreshold: number;
  sellThreshold: number;
  maxPositionPct: number;
  targetRiskPct: number;
  useVolSizing: boolean;
}

type Filter = "all" | "watchlist" | "buys" | "sells";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "watchlist", label: "★ Watchlist" },
  { key: "buys", label: "Buys" },
  { key: "sells", label: "Sells" },
];

export function Recommendations() {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");

  const reco = useQuery({
    queryKey: ["reco"],
    queryFn: () => api.recommendations(false),
    refetchInterval: 30_000,
  });

  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api.settings() });
  const s = settings.data?.settings;
  const sizing: SizingCfg = {
    buyThreshold: s?.buy_threshold ?? 0.25,
    sellThreshold: s?.sell_threshold ?? -0.25,
    maxPositionPct: s?.max_position_pct ?? 0.1,
    targetRiskPct: s?.target_risk_pct ?? 0.01,
    useVolSizing: s?.use_vol_sizing ?? false,
  };

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
  const wlCount = recs.filter((r) => r.in_watchlist).length;

  const shown = recs.filter((r) => {
    if (filter === "watchlist") return r.in_watchlist;
    if (filter === "buys") return r.action === "BUY";
    if (filter === "sells") return r.action === "SELL";
    return true;
  });

  return (
    <div className="space-y-4">
      <RegimeBanner regime={data?.regime} />
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="text-sm text-slate-400">
          {data?.generated_at
            ? `Scanned ${recs.length} symbols (★ ${wlCount} watchlist) · ranked by risk-adjusted score · updated ${new Date(
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

      <div className="flex gap-1.5">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`text-xs font-medium px-3 py-1.5 rounded-full border transition-colors ${
              filter === f.key
                ? "bg-accent/15 border-accent/40 text-accent"
                : "bg-panel border-edge text-slate-400 hover:bg-panel2"
            }`}
          >
            {f.label}
            {f.key === "watchlist" && wlCount > 0 ? ` (${wlCount})` : ""}
          </button>
        ))}
      </div>

      {buy.isError && <ErrorBanner message={(buy.error as Error).message} />}
      {recs.length === 0 && (
        <ErrorBanner message="No recommendations. Configure Alpaca credentials and refresh." />
      )}
      {recs.length > 0 && shown.length === 0 && (
        <p className="text-slate-400 text-sm py-6 text-center">
          No names match this filter.
        </p>
      )}

      <div className="space-y-2">
        {shown.map((r) => (
          <RecoRow
            key={r.symbol}
            r={r}
            sizing={sizing}
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
  sizing,
  expanded,
  onToggle,
  onBuy,
  buying,
}: {
  r: Recommendation;
  sizing: SizingCfg;
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
            {r.in_watchlist && (
              <span className="text-accent mr-1" title="In your watchlist">
                ★
              </span>
            )}
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
        <div className="bg-panel2 px-4 py-4 border-t border-edge space-y-5">
          <ScoreExplainer r={r} sizing={sizing} />
          <SizingExplainer r={r} sizing={sizing} />
          {r.reasons.length > 0 && (
            <div>
              <SectionLabel>Signal notes</SectionLabel>
              <ul className="text-sm text-slate-600 list-disc pl-5 space-y-0.5">
                {r.reasons.map((reason, i) => (
                  <li key={i}>{reason}</li>
                ))}
              </ul>
            </div>
          )}
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

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[11px] font-bold text-slate-400 uppercase tracking-[0.1em] mb-2">
      {children}
    </div>
  );
}

const signed = (n: number, d = 2) => `${n >= 0 ? "+" : ""}${n.toFixed(d)}`;

/**
 * Shows how each signal family's raw score, scaled by its weight, sums into the
 * composite — then how the regime gate and thresholds turn that into the call.
 */
function ScoreExplainer({ r, sizing }: { r: Recommendation; sizing: SizingCfg }) {
  const rows = Object.entries(r.breakdown).map(([name, b]) => ({
    name,
    score: b.score,
    weight: b.weight,
    contribution: b.score * b.weight,
  }));
  const rawComposite = rows.reduce((a, b) => a + b.contribution, 0);
  const mult = r.regime_multiplier ?? 1;
  const dampened = mult < 1 && rawComposite > 0;
  const maxAbs = Math.max(0.01, ...rows.map((x) => Math.abs(x.contribution)));

  return (
    <div>
      <SectionLabel>How the score was computed</SectionLabel>
      <p className="text-xs text-slate-500 mb-3">
        Each signal family scores the stock from −1 to +1, then counts toward the
        total in proportion to its weight (weights shown are renormalized over the
        families with data, so they sum to 100%). The weighted contributions add up
        to the composite score.
      </p>

      <div className="space-y-1.5">
        {rows.map((row) => (
          <div key={row.name} className="flex items-center gap-2 text-xs">
            <div className="w-24 capitalize text-slate-600">{row.name}</div>
            <div className="w-14 text-right font-mono text-slate-500">
              {signed(row.score)}
            </div>
            <div className="w-12 text-right font-mono text-slate-400">
              ×{(row.weight * 100).toFixed(0)}%
            </div>
            <div className="flex-1 relative h-4 bg-panel rounded overflow-hidden min-w-[80px]">
              <div className="absolute left-1/2 top-0 h-full w-px bg-edge" />
              <div
                className={`absolute top-0 h-full ${
                  row.contribution >= 0 ? "bg-buy/60" : "bg-sell/60"
                }`}
                style={
                  row.contribution >= 0
                    ? {
                        left: "50%",
                        width: `${(Math.abs(row.contribution) / maxAbs) * 50}%`,
                      }
                    : {
                        right: "50%",
                        width: `${(Math.abs(row.contribution) / maxAbs) * 50}%`,
                      }
                }
              />
            </div>
            <div
              className={`w-14 text-right font-mono ${
                row.contribution > 0
                  ? "text-buy"
                  : row.contribution < 0
                    ? "text-sell"
                    : "text-slate-400"
              }`}
            >
              {signed(row.contribution, 3)}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3 pt-3 border-t border-edge space-y-1 text-xs">
        <Line label="Weighted sum (composite)" value={signed(rawComposite, 3)} />
        {dampened && (
          <>
            <Line
              label={`Risk-off regime gate ×${mult.toFixed(2)}`}
              value={signed(rawComposite * mult, 3)}
              tone="sell"
            />
            <p className="text-[11px] text-slate-400 pl-1">
              In a risk-off tape longs are throttled; sells are never dampened.
            </p>
          </>
        )}
        <div className="flex items-center justify-between pt-1">
          <span className="font-semibold text-slate-600">Final score</span>
          <span
            className={`font-mono font-bold text-sm ${
              r.score > 0 ? "text-buy" : r.score < 0 ? "text-sell" : "text-slate-500"
            }`}
          >
            {signed(r.score)}
          </span>
        </div>
      </div>

      <ThresholdScale r={r} sizing={sizing} />

      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-slate-500">
        <span>
          Agreement{" "}
          <span className="font-mono text-slate-600">
            {r.agreement != null ? fmtPct(r.agreement, 0) : "—"}
          </span>{" "}
          <span className="text-slate-400">(weight share voting the same way)</span>
        </span>
        <span>
          Conviction{" "}
          <span className="font-mono text-slate-600">
            {r.conviction != null ? r.conviction.toFixed(2) : "—"}
          </span>{" "}
          <span className="text-slate-400">(|score| × agreement)</span>
        </span>
        <span>
          Rank score{" "}
          <span className="font-mono text-slate-600">
            {r.rank_score != null ? r.rank_score.toFixed(3) : "—"}
          </span>{" "}
          <span className="text-slate-400">(score × conviction ÷ ATR%)</span>
        </span>
      </div>
    </div>
  );
}

function Line({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "sell";
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-slate-500">{label}</span>
      <span
        className={`font-mono ${tone === "sell" ? "text-sell" : "text-slate-600"}`}
      >
        {value}
      </span>
    </div>
  );
}

/** A −1…+1 number line marking the BUY/SELL bands and where this score lands. */
function ThresholdScale({ r, sizing }: { r: Recommendation; sizing: SizingCfg }) {
  const toPct = (v: number) => ((Math.max(-1, Math.min(1, v)) + 1) / 2) * 100;
  const buyPct = toPct(sizing.buyThreshold);
  const sellPct = toPct(sizing.sellThreshold);
  const scorePct = toPct(r.score);
  return (
    <div className="mt-3">
      <div className="relative h-6">
        <div className="absolute inset-x-0 top-2.5 h-1.5 rounded-full overflow-hidden flex">
          <div className="bg-sell/30" style={{ width: `${sellPct}%` }} />
          <div className="bg-hold/40" style={{ width: `${buyPct - sellPct}%` }} />
          <div className="bg-buy/30" style={{ width: `${100 - buyPct}%` }} />
        </div>
        <div
          className="absolute top-1 h-4 w-1 rounded-full bg-slate-700"
          style={{ left: `calc(${scorePct}% - 2px)` }}
          title={`score ${signed(r.score)}`}
        />
      </div>
      <div className="flex justify-between text-[10px] text-slate-400">
        <span>SELL ≤ {signed(sizing.sellThreshold)}</span>
        <span>HOLD</span>
        <span>BUY ≥ {signed(sizing.buyThreshold)}</span>
      </div>
    </div>
  );
}

/** Plain-language "how much to trade" with the sizing math spelled out. */
function SizingExplainer({ r, sizing }: { r: Recommendation; sizing: SizingCfg }) {
  const price = r.price ?? 0;
  const weight = r.suggested_weight_pct;
  const qty = r.suggested_qty;
  const dollars = qty != null && price ? qty * price : null;

  if (r.action === "SELL") {
    return (
      <div>
        <SectionLabel>How much to sell</SectionLabel>
        <p className="text-sm text-slate-600">
          Score is in the SELL band — if you hold {r.symbol}, exit (or trim) the
          position. The simulator is long-only, so there's no short to size; sells
          close existing shares only.
        </p>
      </div>
    );
  }

  if (r.action === "HOLD") {
    return (
      <div>
        <SectionLabel>How much to trade</SectionLabel>
        <p className="text-sm text-slate-600">
          Score sits in the neutral band, so no new position is sized. No action
          suggested.
          {r.liquidity_warning ? ` Note: ${r.liquidity_warning}.` : ""}
        </p>
      </div>
    );
  }

  // BUY
  const rawVol =
    r.atr_pct && r.atr_pct > 0 ? sizing.targetRiskPct / Math.max(r.atr_pct, 0.005) : null;
  return (
    <div>
      <SectionLabel>How much to buy</SectionLabel>
      <div className="flex items-baseline gap-2 mb-2">
        <span className="text-lg font-bold text-buy">
          {qty != null ? `≈ ${qty.toLocaleString()} shares` : "—"}
        </span>
        {dollars != null && (
          <span className="text-sm text-slate-500">
            ≈ {fmtUsd(dollars)}
            {weight != null ? ` · ${fmtPct(weight, 1)} of equity` : ""}
          </span>
        )}
      </div>
      {qty == null && (
        <p className="text-xs text-slate-400 mb-2">
          Connect a funded account to size in shares — the target weight below still
          applies.
        </p>
      )}
      <div className="text-xs text-slate-500 leading-relaxed">
        {sizing.useVolSizing ? (
          <>
            <span className="font-medium text-slate-600">Volatility-targeted size.</span>{" "}
            Target risk {fmtPct(sizing.targetRiskPct, 1)} ÷ ATR{" "}
            {r.atr_pct != null ? fmtPct(r.atr_pct, 1) : "—"} ={" "}
            {rawVol != null ? fmtPct(rawVol, 1) : "—"}, capped at the{" "}
            {fmtPct(sizing.maxPositionPct, 0)} max position and scaled by conviction{" "}
            {r.conviction != null ? `(${r.conviction.toFixed(2)})` : ""} →{" "}
            <span className="font-mono text-slate-600">
              {weight != null ? fmtPct(weight, 1) : "—"}
            </span>{" "}
            of equity. Lower-volatility names earn a bigger weight so each position
            carries comparable risk.
          </>
        ) : (
          <>
            <span className="font-medium text-slate-600">Fixed sizing.</span> Buys use
            the flat {fmtPct(sizing.maxPositionPct, 0)} max-position weight
            {weight != null ? ` (≈ ${fmtPct(weight, 1)} here)` : ""}. Turn on
            volatility-targeted sizing in Settings to scale by risk and conviction.
          </>
        )}
        {qty != null && price > 0 && (
          <>
            {" "}
            Shares = equity × {weight != null ? fmtPct(weight, 1) : "—"} ÷{" "}
            {fmtUsd(price)}.
          </>
        )}
      </div>
      {r.liquidity_warning && (
        <p className="text-xs text-sell mt-2">⚠ {r.liquidity_warning}</p>
      )}
    </div>
  );
}
