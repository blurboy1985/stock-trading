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
          <SignalNotes r={r} />
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
      <p className="text-xs text-slate-400 mb-3">
        Each family scores −1…+1, weighted (renormalized to 100%) into the composite.
      </p>

      <div className="space-y-1.5">
        {rows.map((row) => (
          <div key={row.name} className="flex items-center gap-2 text-xs">
            <div className="w-24 capitalize text-slate-300">{row.name}</div>
            <div className="w-14 text-right font-mono text-slate-300">
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
          <span className="font-semibold text-slate-200">Final score</span>
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

      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-slate-400">
        <span>
          Agreement{" "}
          <span className="font-mono text-slate-300">
            {r.agreement != null ? fmtPct(r.agreement, 0) : "—"}
          </span>
        </span>
        <span>
          Conviction{" "}
          <span className="font-mono text-slate-300">
            {r.conviction != null ? r.conviction.toFixed(2) : "—"}
          </span>{" "}
          (|score| × agreement)
        </span>
        <span>
          Rank{" "}
          <span className="font-mono text-slate-300">
            {r.rank_score != null ? r.rank_score.toFixed(3) : "—"}
          </span>{" "}
          (score × conviction ÷ ATR%)
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
      <span className="text-slate-400">{label}</span>
      <span
        className={`font-mono ${tone === "sell" ? "text-sell" : "text-slate-200"}`}
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
        <p className="text-sm text-slate-300">
          SELL band — exit or trim if you hold {r.symbol}. Long-only, so sells close
          existing shares only.
        </p>
      </div>
    );
  }

  if (r.action === "HOLD") {
    return (
      <div>
        <SectionLabel>How much to trade</SectionLabel>
        <p className="text-sm text-slate-300">
          Neutral band — no new position sized.
          {r.liquidity_warning ? ` Note: ${r.liquidity_warning}.` : ""}
        </p>
      </div>
    );
  }

  // BUY
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
          Connect a funded account to size in shares — the target weight still applies.
        </p>
      )}
      <div className="text-xs text-slate-300 leading-relaxed">
        {sizing.useVolSizing ? (
          <>
            <span className="font-medium text-slate-200">Volatility-targeted.</span>{" "}
            Risk {fmtPct(sizing.targetRiskPct, 1)} ÷ ATR{" "}
            {r.atr_pct != null ? fmtPct(r.atr_pct, 1) : "—"}, capped at{" "}
            {fmtPct(sizing.maxPositionPct, 0)} and scaled by conviction →{" "}
            <span className="font-mono text-slate-200">
              {weight != null ? fmtPct(weight, 1) : "—"}
            </span>{" "}
            of equity.
          </>
        ) : (
          <>
            <span className="font-medium text-slate-200">Fixed sizing</span> at the flat{" "}
            {fmtPct(sizing.maxPositionPct, 0)} max-position weight
            {weight != null ? ` (≈ ${fmtPct(weight, 1)})` : ""}.
          </>
        )}
        {qty != null && price > 0 && (
          <> Shares = equity × {weight != null ? fmtPct(weight, 1) : "—"} ÷ {fmtUsd(price)}.</>
        )}
      </div>
      {r.liquidity_warning && (
        <p className="text-xs text-sell mt-2">⚠ {r.liquidity_warning}</p>
      )}
    </div>
  );
}

// What each signal family actually measures — shown next to its notes so a
// reason like "RSI 28 oversold" is anchored to the family (and weight) it feeds.
const FAMILY_INFO: Record<string, { label: string; about: string }> = {
  technical: {
    label: "Technical",
    about: "RSI, MACD & ADX-confirmed MA-crossover trend.",
  },
  volatility: {
    label: "Volatility",
    about: "Donchian/Bollinger breakouts & volume spikes.",
  },
  momentum: {
    label: "Momentum",
    about: "Cross-sectional relative strength vs the universe.",
  },
  sentiment: {
    label: "Sentiment",
    about: "Recency-weighted, finance-tuned news polarity.",
  },
  fundamentals: {
    label: "Fundamentals",
    about: "Sector-relative value, growth, quality & balance-sheet health.",
  },
};

const FAMILY_ORDER = ["technical", "volatility", "momentum", "sentiment", "fundamentals"];

// Per-indicator plain-language definitions + an external reference, shown when a
// signal note is expanded. Keyed by an indicator id; reasons are mapped to an id
// by keyword (see indicatorForReason). Anything unmatched falls back to the
// family-level blurb so every note still gets a definition.
const INDICATOR_INFO: Record<string, { blurb: string; href: string }> = {
  rsi: {
    blurb:
      "RSI measures momentum on a 0–100 scale. Below 30 is oversold (often due a bounce), above 70 overbought.",
    href: "https://www.investopedia.com/terms/r/rsi.asp",
  },
  macd: {
    blurb:
      "MACD tracks trend momentum; a positive, rising histogram means upside momentum is building.",
    href: "https://www.investopedia.com/terms/m/macd.asp",
  },
  adx: {
    blurb:
      "ADX gauges trend strength (not direction). Above ~25 confirms a real trend rather than chop.",
    href: "https://www.investopedia.com/terms/a/adx.asp",
  },
  sma: {
    blurb:
      "Moving-average crossover: a 20-day average above the 50-day signals a developing uptrend.",
    href: "https://www.investopedia.com/terms/s/sma.asp",
  },
  donchian: {
    blurb:
      "A Donchian breakout is a close beyond the highest/lowest price of the prior N days — a classic trend trigger.",
    href: "https://www.investopedia.com/terms/d/donchianchannels.asp",
  },
  volume: {
    blurb:
      "A volume spike (multiple of the average) shows conviction behind a move rather than a quiet drift.",
    href: "https://www.investopedia.com/terms/v/volume.asp",
  },
  atr: {
    blurb:
      "ATR is the average daily range — a volatility gauge used to size positions so each carries similar risk.",
    href: "https://www.investopedia.com/terms/a/atr.asp",
  },
  momentum: {
    blurb:
      "Cross-sectional momentum ranks each name's trailing return against the scanned universe; leaders tend to persist.",
    href: "https://www.investopedia.com/terms/m/momentum.asp",
  },
  sentiment: {
    blurb:
      "News sentiment is a recency-weighted, finance-tuned polarity score over recent headlines for the symbol.",
    href: "https://www.investopedia.com/terms/m/marketsentiment.asp",
  },
  pe: {
    blurb:
      "P/E compares price to earnings; judged here against the sector median rather than in absolute terms.",
    href: "https://www.investopedia.com/terms/p/price-earningsratio.asp",
  },
  growth: {
    blurb: "Revenue/earnings growth — how fast the business is expanding year over year.",
    href: "https://www.investopedia.com/terms/r/revenue.asp",
  },
  margins: {
    blurb: "Profit margin is the share of revenue kept as profit — a core quality/efficiency read.",
    href: "https://www.investopedia.com/terms/p/profitmargin.asp",
  },
  roe: {
    blurb: "Return on equity measures how much profit a company generates per dollar of shareholder equity.",
    href: "https://www.investopedia.com/terms/r/returnonequity.asp",
  },
  leverage: {
    blurb: "Debt-to-equity gauges balance-sheet risk; high leverage amplifies both gains and losses.",
    href: "https://www.investopedia.com/terms/d/debtequityratio.asp",
  },
};

// Map a free-text reason to an indicator id by keyword. Returns null when no
// specific indicator matches (caller falls back to the family blurb).
function indicatorForReason(reason: string): string | null {
  const t = reason.toLowerCase();
  if (t.includes("rsi")) return "rsi";
  if (t.includes("macd")) return "macd";
  if (t.includes("adx") || t.includes("trend")) return "adx";
  if (t.includes("sma") || t.includes("moving average")) return "sma";
  if (t.includes("breakout") || t.includes("breakdown") || t.includes("donchian")) return "donchian";
  if (t.includes("volume")) return "volume";
  if (t.includes("atr") || t.includes("volatility")) return "atr";
  if (t.includes("strength") || t.includes("rank") || t.includes("momentum")) return "momentum";
  if (t.includes("sentiment") || t.includes("news")) return "sentiment";
  if (t.includes("p/e") || t.includes("pe ")) return "pe";
  if (t.includes("growth") || t.includes("revenue") || t.includes("shrinking")) return "growth";
  if (t.includes("margin")) return "margins";
  if (t.includes("roe")) return "roe";
  if (t.includes("leverage") || t.includes("d/e")) return "leverage";
  return null;
}

const fmtMetric = (v: number | string | null): string => {
  if (v == null) return "—";
  if (typeof v === "string") return v;
  if (Number.isNaN(v)) return "—";
  return Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(2);
};

// The metric keys worth surfacing per family, in display order, with labels.
const FAMILY_METRICS: Record<string, { key: string; label: string; fmt?: (n: number) => string }[]> = {
  technical: [
    { key: "rsi", label: "RSI" },
    { key: "macd_hist", label: "MACD hist" },
    { key: "adx", label: "ADX" },
    { key: "sma20", label: "SMA20" },
    { key: "sma50", label: "SMA50" },
  ],
  volatility: [
    { key: "atr_pct", label: "ATR%", fmt: (n) => fmtPct(n, 1) },
    { key: "volume_ratio", label: "Vol ×" },
    { key: "donchian_high", label: "20d high" },
    { key: "donchian_low", label: "20d low" },
  ],
  momentum: [
    { key: "rank", label: "Rank" },
    { key: "universe", label: "of" },
    { key: "percentile", label: "Pctile", fmt: (n) => fmtPct(n, 0) },
    { key: "zscore", label: "z-score" },
  ],
  sentiment: [
    { key: "avg_polarity", label: "Polarity" },
    { key: "positive", label: "Pos" },
    { key: "negative", label: "Neg" },
    { key: "count", label: "Stories" },
    { key: "backend", label: "Via" },
  ],
  fundamentals: [
    { key: "trailing_pe", label: "P/E" },
    { key: "revenue_growth", label: "Rev growth", fmt: (n) => fmtPct(n, 0) },
    { key: "profit_margins", label: "Margin", fmt: (n) => fmtPct(n, 0) },
    { key: "roe", label: "ROE", fmt: (n) => fmtPct(n, 0) },
    { key: "debt_to_equity", label: "D/E" },
  ],
};

/**
 * Signal notes, grouped by the family that produced them — each note sits under
 * its family's score and weight so you can see which signal said what and how
 * much it counted toward the composite.
 */
function SignalNotes({ r }: { r: Recommendation }) {
  // One note open at a time, keyed `${family}:${index}`.
  const [openNote, setOpenNote] = useState<string | null>(null);

  const families = Object.keys(r.breakdown).sort(
    (a, b) => FAMILY_ORDER.indexOf(a) - FAMILY_ORDER.indexOf(b),
  );

  // Reasons attached to a family (vs. top-level notes like the liquidity
  // guardrail, which scoring prepends outside any family's breakdown).
  const familyReasons = new Set<string>();
  for (const f of families) {
    for (const reason of r.breakdown[f]?.reasons ?? []) familyReasons.add(reason);
  }
  const otherNotes = r.reasons.filter((x) => !familyReasons.has(x));

  // Lazily fetch recent headlines only while a sentiment note is open — they're
  // the evidence corpus behind the sentiment score (scoring doesn't persist the
  // exact stories, so we show the symbol's current recent news).
  const sentimentOpen = openNote?.startsWith("sentiment:") ?? false;
  const news = useQuery({
    queryKey: ["recoNews", r.symbol],
    queryFn: () => api.news(r.symbol),
    enabled: sentimentOpen,
    staleTime: 5 * 60_000,
  });

  const renderNote = (family: string, reason: string, i: number) => {
    const key = `${family}:${i}`;
    const open = openNote === key;
    return (
      <li key={i} className="text-slate-200">
        <span>{reason}</span>{" "}
        <button
          onClick={() => setOpenNote(open ? null : key)}
          className={`align-middle text-sm leading-none transition-colors ${
            open ? "text-accent" : "text-slate-400 hover:text-accent"
          }`}
          title="Show evidence & definition"
          aria-label="Show evidence and definition"
        >
          ⓘ
        </button>
        {open && (
          <NoteEvidence
            family={family}
            reason={reason}
            r={r}
            news={family === "sentiment" ? news.data?.news ?? [] : null}
            newsLoading={family === "sentiment" && news.isLoading}
          />
        )}
      </li>
    );
  };

  return (
    <div>
      <SectionLabel>Signal notes</SectionLabel>
      <p className="text-[11px] text-slate-400 mb-2">
        Tap <span className="text-accent">ⓘ</span> on any note for its definition, the
        live numbers behind it, and sources.
      </p>
      <div className="space-y-2.5">
        {families.map((f) => {
          const b = r.breakdown[f];
          if (!b) return null;
          const info = FAMILY_INFO[f] ?? { label: f, about: "" };
          return (
            <div key={f} className="text-sm">
              <div className="flex items-baseline gap-2">
                <span className="font-semibold text-slate-100 capitalize">
                  {info.label}
                </span>
                <span
                  className={`font-mono text-xs ${
                    b.score > 0
                      ? "text-buy"
                      : b.score < 0
                        ? "text-sell"
                        : "text-slate-400"
                  }`}
                >
                  {signed(b.score)}
                </span>
              </div>
              {b.reasons.length > 0 ? (
                <ul className="text-sm list-disc pl-5 space-y-1 mt-0.5">
                  {b.reasons.map((reason, i) => renderNote(f, reason, i))}
                </ul>
              ) : (
                <p className="text-xs text-slate-400 pl-5 mt-0.5 italic">
                  no notable signal — neutral contribution
                </p>
              )}
            </div>
          );
        })}

        {otherNotes.length > 0 && (
          <div className="text-sm pt-1 border-t border-edge/60">
            <span className="font-semibold text-slate-100">Other</span>
            <ul className="text-sm list-disc pl-5 space-y-1 mt-0.5">
              {otherNotes.map((reason, i) => renderNote("other", reason, i))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

/** Inline evidence revealed under a clicked signal note. */
function NoteEvidence({
  family,
  reason,
  r,
  news,
  newsLoading,
}: {
  family: string;
  reason: string;
  r: Recommendation;
  news: { headline: string; url: string; source: string }[] | null;
  newsLoading: boolean;
}) {
  const indicatorId = indicatorForReason(reason);
  const def =
    (indicatorId && INDICATOR_INFO[indicatorId]) ||
    // Fall back to the family blurb so every note has a definition + reference.
    (family !== "other"
      ? { blurb: FAMILY_INFO[family]?.about ?? "", href: INDICATOR_INFO[family]?.href ?? "" }
      : null);

  const metrics = r.breakdown[family]?.metrics ?? {};
  const chips = (FAMILY_METRICS[family] ?? [])
    .map((m) => {
      const raw = metrics[m.key];
      if (raw == null || raw === "") return null;
      const value =
        typeof raw === "number" && m.fmt ? m.fmt(raw) : fmtMetric(raw as number | string);
      return { label: m.label, value };
    })
    .filter((x): x is { label: string; value: string } => x !== null);

  return (
    <div className="mt-1.5 mb-1 rounded-lg border border-edge bg-panel px-3 py-2.5 space-y-2">
      {def?.blurb && (
        <p className="text-xs text-slate-300 leading-relaxed">
          {def.blurb}
          {def.href && (
            <>
              {" "}
              <a
                href={def.href}
                target="_blank"
                rel="noreferrer"
                className="text-accent hover:underline whitespace-nowrap"
              >
                Learn more ↗
              </a>
            </>
          )}
        </p>
      )}

      {chips.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {chips.map((c) => (
            <span
              key={c.label}
              className="text-[11px] font-mono rounded bg-panel2 border border-edge px-1.5 py-0.5 text-slate-300"
            >
              <span className="text-slate-400">{c.label}</span>{" "}
              <span className="text-slate-100">{c.value}</span>
            </span>
          ))}
        </div>
      )}

      {family === "sentiment" && (
        <div>
          <div className="text-[11px] text-slate-400 mb-1">Recent news for {r.symbol}</div>
          {newsLoading ? (
            <p className="text-xs text-slate-400">Loading headlines…</p>
          ) : news && news.length > 0 ? (
            <ul className="space-y-1">
              {news.slice(0, 5).map((n, i) => (
                <li key={i} className="text-xs leading-snug">
                  <a
                    href={n.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-slate-200 hover:text-accent"
                  >
                    {n.headline}
                  </a>
                  {n.source && <span className="text-slate-400 ml-1.5">· {n.source}</span>}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-slate-400">No recent headlines found.</p>
          )}
        </div>
      )}

      <Link
        to={`/ticker/${r.symbol}`}
        className="inline-block text-xs text-accent hover:underline"
      >
        View {r.symbol} chart →
      </Link>
    </div>
  );
}
