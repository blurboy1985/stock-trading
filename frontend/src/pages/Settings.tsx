import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type AppSettings } from "../api/client";
import { Panel, Spinner, ErrorBanner, fmtPct } from "../components/ui";
import { LimitationsPanel } from "../components/Disclosures";
import { openTradeGuide } from "../components/TradeWalkthrough";

const SIGNALS = ["technical", "volatility", "momentum", "sentiment", "fundamentals"];

const NEWS_SOURCE_LABELS: Record<string, string> = {
  alpaca: "Alpaca (Benzinga)",
  yfinance: "Yahoo Finance",
  finnhub: "Finnhub",
  marketaux: "Marketaux",
  newsapi: "NewsAPI",
};

export function Settings() {
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [draft, setDraft] = useState<AppSettings["settings"] | null>(null);
  const [newSym, setNewSym] = useState("");

  useEffect(() => {
    if (settings.data) setDraft(settings.data.settings);
  }, [settings.data]);

  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.updateSettings(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  });
  const addSym = useMutation({
    mutationFn: (s: string) => api.addSymbol(s),
    onSuccess: () => {
      setNewSym("");
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
  });
  const removeSym = useMutation({
    mutationFn: (s: string) => api.removeSymbol(s),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  });
  const syncWl = useMutation({ mutationFn: () => api.syncWatchlist() });

  if (settings.isLoading || !draft) return <Spinner />;
  const broker = settings.data!.broker;
  const watchlist = settings.data!.watchlist;
  const newsInfo = settings.data!.news;

  const update = (k: keyof typeof draft, v: unknown) => setDraft({ ...draft, [k]: v } as any);

  return (
    <div className="space-y-5">
      {/* Broker / safety status */}
      <Panel title="Broker & Safety">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
          <StatusRow ok={broker.has_credentials} label="Alpaca credentials" />
          <StatusRow ok={broker.is_paper} label="Paper mode" warnIfFalse />
          <StatusRow
            ok={!broker.live_trading_enabled}
            label="Live trading locked"
            warnIfFalse
          />
        </div>
        {broker.live_trading_enabled && (
          <div className="mt-3 bg-sell/10 border border-sell/40 text-sell rounded-lg px-4 py-2 text-sm">
            ⚠ LIVE TRADING IS ENABLED — orders use real money.
          </div>
        )}
        {!broker.has_credentials && (
          <ErrorBanner message="Add APCA_API_KEY_ID and APCA_API_SECRET_KEY to backend/.env, then restart the backend." />
        )}
      </Panel>

      {/* Auto-trade */}
      <Panel title="Automation">
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={draft.auto_trade}
            onChange={(e) => update("auto_trade", e.target.checked)}
            className="w-4 h-4 accent-blue-500"
          />
          <span className="text-sm">
            Auto-propose trades during market hours
            <span className="text-slate-500">
              {" "}
              — you confirm each one before any order is placed (paper only). Review
              proposals on the Automation tab.
            </span>
          </span>
        </label>
      </Panel>

      {/* Universe */}
      <Panel title="Universe">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <label className="block">
            <span className="text-xs text-slate-400">Scan source</span>
            <select
              value={draft.universe_source ?? "most_active"}
              onChange={(e) => update("universe_source", e.target.value)}
              className="inp"
            >
              <option value="most_active">
                Most-active US stocks (broad daily scan)
              </option>
              <option value="core_liquid">
                Core liquid set (stable ~120 large/mid-caps) — best for swing RS
              </option>
              <option value="watchlist">My watchlist only (faster)</option>
            </select>
            <span className="text-[11px] text-slate-500">
              Most-active is recency-biased (today's churn). The core liquid set
              ranks a <em>stable</em> pond by relative strength, so momentum
              leaders persist — recommended for swing trading. All sources always
              include your watchlist (★).
            </span>
          </label>
          <NumField
            label="Max symbols per scan"
            value={draft.universe_size ?? 75}
            step={5}
            onChange={(v) => update("universe_size", Math.round(v))}
          />
        </div>
      </Panel>

      {/* Signal weights */}
      <Panel title="Signal Weights">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {SIGNALS.map((s) => (
            <label key={s} className="block">
              <span className="text-xs text-slate-400 capitalize">{s}</span>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={draft.weights[s] ?? 0}
                onChange={(e) =>
                  update("weights", { ...draft.weights, [s]: Number(e.target.value) })
                }
                className="w-full accent-blue-500"
              />
              <span className="text-sm font-mono">{(draft.weights[s] ?? 0).toFixed(2)}</span>
            </label>
          ))}
        </div>
        <p className="text-xs text-slate-500 mt-2">
          Weights are auto-normalized across active signals at scoring time.
          Sentiment & fundamentals are skipped in backtests, and in the default
          veto-only mode they carry no weight here (see Sentiment & Fundamentals).
        </p>
      </Panel>

      {/* Sentiment & fundamentals tuning */}
      <Panel title="Sentiment & Fundamentals">
        <label className="block mb-4">
          <span className="text-xs text-slate-400">How they're used</span>
          <select
            value={draft.context_signal_mode ?? "filter"}
            onChange={(e) => update("context_signal_mode", e.target.value)}
            className="inp"
          >
            <option value="filter">
              Veto only (recommended) — keep them out of the score, block clearly
              negative buys
            </option>
            <option value="blend">Blend into the weighted score (legacy)</option>
          </select>
          <span className="text-[11px] text-slate-500">
            Sentiment & fundamentals have no point-in-time history, so they can't
            be backtested. Veto-only keeps the return-driving score on the{" "}
            <em>validated</em> price signals and uses these only to suppress a buy
            when clearly negative — closing the live-vs-backtest gap.
          </span>
        </label>
        {draft.context_signal_mode !== "blend" && (
          <div className="mb-4 max-w-xs">
            <NumField
              label="Veto threshold (|score| below −this blocks a buy)"
              value={draft.context_veto_threshold ?? 0.4}
              step={0.05}
              onChange={(v) => update("context_veto_threshold", v)}
            />
          </div>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <label className="block">
            <span className="text-xs text-slate-400">Sentiment engine</span>
            <select
              value={draft.sentiment_backend ?? "lexicon"}
              onChange={(e) => update("sentiment_backend", e.target.value)}
              className="inp"
            >
              <option value="lexicon">Lexicon (VADER + Loughran–McDonald)</option>
              <option value="llm">Claude (LLM) — uses Claude Code subscription</option>
            </select>
            <span className="text-[11px] text-slate-500">
              LLM runs via the local Claude Code CLI (no API key); falls back to
              the lexicon on any error.
            </span>
          </label>
          <NumField
            label="News half-life (days)"
            value={draft.sentiment_halflife_days ?? 3}
            step={0.5}
            onChange={(v) => update("sentiment_halflife_days", v)}
          />
          <label className="block">
            <span className="text-xs text-slate-400">
              Finance-lexicon weight (vs VADER)
            </span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={draft.sentiment_lm_weight ?? 0.5}
              onChange={(e) => update("sentiment_lm_weight", Number(e.target.value))}
              className="w-full accent-blue-500"
            />
            <span className="text-sm font-mono">
              {(draft.sentiment_lm_weight ?? 0.5).toFixed(2)}
            </span>
          </label>
          <label className="flex items-center gap-2 text-sm cursor-pointer mt-5">
            <input
              type="checkbox"
              checked={draft.fundamentals_sector_relative ?? true}
              onChange={(e) =>
                update("fundamentals_sector_relative", e.target.checked)
              }
              className="w-4 h-4 accent-blue-500"
            />
            Score valuation relative to sector peers
          </label>
        </div>
      </Panel>

      {/* News sources */}
      <Panel title="News Sources (sentiment)">
        <p className="text-xs text-slate-500 mb-3">
          Which feeds power the sentiment signal. Alpaca (Benzinga) is the fast
          batched default. Extra sources are fetched per-symbol and merged with{" "}
          <span className="text-slate-400">event-level de-duplication</span> — the
          same story across many outlets is collapsed to one event, so duplicate
          coverage can't bias the score.
        </p>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mb-4">
          {(newsInfo?.all_sources ?? ["alpaca"]).map((src) => {
            const selected = (draft.news_sources ?? ["alpaca"]).includes(src);
            const available = (newsInfo?.available_sources ?? ["alpaca"]).includes(src);
            return (
              <label
                key={src}
                className={`flex items-center gap-2 text-sm rounded-lg border px-3 py-2 ${
                  available
                    ? "cursor-pointer bg-panel2 border-edge hover:bg-edge"
                    : "opacity-50 bg-panel2 border-edge cursor-not-allowed"
                }`}
                title={
                  available
                    ? ""
                    : `Add ${src.toUpperCase()}_API_KEY to backend/.env to enable`
                }
              >
                <input
                  type="checkbox"
                  disabled={!available}
                  checked={selected && available}
                  onChange={() => {
                    const cur = draft.news_sources ?? ["alpaca"];
                    update(
                      "news_sources",
                      cur.includes(src)
                        ? cur.filter((s) => s !== src)
                        : [...cur, src],
                    );
                  }}
                  className="w-4 h-4 accent-blue-500"
                />
                <span className="capitalize">{NEWS_SOURCE_LABELS[src] ?? src}</span>
                {!available && src !== "alpaca" && src !== "yfinance" && (
                  <span className="text-[10px] text-slate-500 ml-auto">needs key</span>
                )}
              </label>
            );
          })}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <label className="block">
            <span className="text-xs text-slate-400">
              Apply extra sources to
            </span>
            <select
              value={draft.news_scope ?? "watchlist"}
              onChange={(e) => update("news_scope", e.target.value)}
              className="inp"
            >
              <option value="watchlist">My watchlist only (fast)</option>
              <option value="universe">Entire scanned universe (slow)</option>
            </select>
            <span className="text-[11px] text-slate-500">
              Extra feeds make a per-symbol HTTP call; scoping to the watchlist
              keeps a broad scan fast. Alpaca always covers the full universe.
            </span>
          </label>
          <NumField
            label="Headlines per source / symbol"
            value={draft.news_per_source_limit ?? 15}
            step={5}
            onChange={(v) => update("news_per_source_limit", Math.round(v))}
          />
        </div>
      </Panel>

      {/* Quant controls */}
      <Panel title="Quant Controls">
        <div className="flex flex-wrap gap-6 mb-4">
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={draft.regime_filter ?? true}
              onChange={(e) => update("regime_filter", e.target.checked)}
              className="w-4 h-4 accent-blue-500"
            />
            Market regime filter (dampen longs in risk-off tape)
          </label>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={draft.use_vol_sizing ?? true}
              onChange={(e) => update("use_vol_sizing", e.target.checked)}
              className="w-4 h-4 accent-blue-500"
            />
            Volatility-targeted position sizing
          </label>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <label className="block">
            <span className="text-xs text-slate-400">Benchmark</span>
            <input
              value={draft.benchmark_symbol ?? "SPY"}
              onChange={(e) => update("benchmark_symbol", e.target.value.toUpperCase())}
              className="inp"
            />
          </label>
          <NumField
            label="Target risk/position"
            value={draft.target_risk_pct ?? 0.0025}
            step={0.0005}
            onChange={(v) => update("target_risk_pct", v)}
          />
          <NumField
            label="Min $ volume"
            value={draft.min_dollar_volume ?? 5_000_000}
            step={1_000_000}
            onChange={(v) => update("min_dollar_volume", v)}
          />
          <NumField
            label="Min price"
            value={draft.min_price ?? 5}
            step={1}
            onChange={(v) => update("min_price", v)}
          />
          <label className="block">
            <NumField
              label="Regime hard gate (block new longs ≤)"
              value={draft.regime_hard_gate ?? -0.5}
              step={0.1}
              onChange={(v) => update("regime_hard_gate", v)}
            />
            <span className="text-[11px] text-slate-500">
              Regime score runs −1…+1. New longs are blocked outright when it's
              at/below this (capital preservation in a clearly risk-off tape).
              Set −1 to effectively disable.
            </span>
          </label>
          <label className="block">
            <NumField
              label="Earnings blackout (days)"
              value={draft.earnings_blackout_days ?? 5}
              step={1}
              onChange={(v) => update("earnings_blackout_days", Math.round(v))}
            />
            <span className="text-[11px] text-slate-500">
              Suppress new buys within N days of the next earnings report (gap
              risk). 0 disables.
            </span>
          </label>
          <Slider
            label="Max sector exposure"
            value={draft.max_sector_exposure_pct ?? 0.4}
            onChange={(v) => update("max_sector_exposure_pct", v)}
            max={1}
          />
        </div>
      </Panel>

      {/* Risk */}
      <Panel title="Risk Limits">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Slider
            label="Max position"
            value={draft.max_position_pct}
            onChange={(v) => update("max_position_pct", v)}
          />
          <Slider
            label="Max total exposure"
            value={draft.max_total_exposure_pct}
            onChange={(v) => update("max_total_exposure_pct", v)}
            max={1}
          />
          <Slider
            label="Stop loss"
            value={draft.stop_loss_pct}
            onChange={(v) => update("stop_loss_pct", v)}
            max={0.3}
          />
          <Slider
            label="Take profit"
            value={draft.take_profit_pct}
            onChange={(v) => update("take_profit_pct", v)}
            max={0.5}
          />
          <label className="block">
            <NumField
              label="ATR stop multiple"
              value={draft.atr_stop_mult ?? 0}
              step={0.5}
              onChange={(v) => update("atr_stop_mult", v)}
            />
            <span className="text-[11px] text-slate-500">
              When &gt; 0, the stop is placed this many ATRs below entry
              (volatility-scaled, adapts per name) — overrides the flat stop %.
              Backtests favor ~2.5–3×. 0 keeps the flat % stop.
            </span>
          </label>
        </div>
        <p className="text-[11px] text-slate-500 mt-2">
          A volatility-scaled stop sizes risk consistently across quiet and wild
          names. An ATR trailing stop (lets winners run) is available in the
          Backtest tab and applies to live brackets via the broker.
        </p>
      </Panel>

      <div className="flex items-center gap-3">
        <button
          onClick={() => save.mutate(draft)}
          disabled={save.isPending}
          className="bg-accent text-white px-5 py-2 rounded-lg hover:bg-accent/80 disabled:opacity-50"
        >
          {save.isPending ? "Saving…" : "Save settings"}
        </button>
        {save.isSuccess && <span className="text-buy text-sm">Saved ✓</span>}
      </div>

      {/* Watchlist */}
      <Panel title="Watchlist">
        <div className="flex flex-wrap gap-2 mb-3">
          {watchlist.map((s) => (
            <span
              key={s}
              className="bg-panel2 border border-edge rounded-lg px-3 py-1 text-sm flex items-center gap-2"
            >
              {s}
              <button onClick={() => removeSym.mutate(s)} className="text-slate-500 hover:text-sell">
                ×
              </button>
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            value={newSym}
            onChange={(e) => setNewSym(e.target.value.toUpperCase())}
            placeholder="Add symbol (e.g. NVDA)"
            className="inp max-w-xs"
            onKeyDown={(e) => e.key === "Enter" && newSym && addSym.mutate(newSym)}
          />
          <button
            onClick={() => newSym && addSym.mutate(newSym)}
            className="bg-panel2 border border-edge px-4 rounded-lg hover:bg-edge text-sm"
          >
            Add
          </button>
          <button
            onClick={() => syncWl.mutate()}
            disabled={syncWl.isPending || !broker.has_credentials}
            className="ml-auto bg-accent/20 border border-accent/40 text-accent px-4 rounded-lg hover:bg-accent/30 text-sm disabled:opacity-40"
            title="Push this watchlist to a 'StockSim' watchlist on your Alpaca account"
          >
            {syncWl.isPending ? "Syncing…" : "Sync to Alpaca"}
          </button>
        </div>
        {syncWl.isSuccess && (
          <p className="text-buy text-xs mt-2">
            Synced {syncWl.data.symbols.length} symbols to the “{syncWl.data.name}”
            watchlist on Alpaca ({syncWl.data.action}) — view it on the Alpaca site.
          </p>
        )}
        {syncWl.isError && (
          <p className="text-sell text-xs mt-2">{(syncWl.error as Error).message}</p>
        )}
        <p className="text-[11px] text-slate-500 mt-2">
          Watchlist changes auto-sync to Alpaca; orders, positions, and account
          balances already live on your Alpaca paper account and appear when you
          log in to the Alpaca site.
        </p>
      </Panel>

      <Panel title="Getting Started">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <p className="text-sm text-slate-400 max-w-md">
            New here, or want a refresher? Replay the broker's walkthrough — a
            guided tour of how to find an idea, read its thesis, place a buy, and
            sell or close a position.
          </p>
          <button
            onClick={openTradeGuide}
            className="bg-accent/15 border border-accent/40 text-accent text-sm px-4 py-2 rounded-lg hover:bg-accent/25 whitespace-nowrap"
          >
            Replay walkthrough →
          </button>
        </div>
      </Panel>

      <LimitationsPanel />
    </div>
  );
}

function StatusRow({
  ok,
  label,
  warnIfFalse,
}: {
  ok: boolean;
  label: string;
  warnIfFalse?: boolean;
}) {
  const color = ok ? "text-buy" : warnIfFalse ? "text-sell" : "text-slate-400";
  return (
    <div className="flex items-center gap-2 bg-panel2 rounded-lg px-3 py-2">
      <span className={color}>{ok ? "●" : "○"}</span>
      <span>{label}</span>
    </div>
  );
}

function NumField({
  label,
  value,
  onChange,
  step = 1,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  step?: number;
}) {
  return (
    <label className="block">
      <span className="text-xs text-slate-400">{label}</span>
      <input
        type="number"
        value={value}
        step={step}
        onChange={(e) => onChange(Number(e.target.value))}
        className="inp"
      />
    </label>
  );
}

function Slider({
  label,
  value,
  onChange,
  max = 0.5,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  max?: number;
}) {
  return (
    <label className="block">
      <span className="text-xs text-slate-400">{label}</span>
      <input
        type="range"
        min={0}
        max={max}
        step={0.01}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-blue-500"
      />
      <span className="text-sm font-mono">{fmtPct(value)}</span>
    </label>
  );
}
