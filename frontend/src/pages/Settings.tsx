import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type AppSettings } from "../api/client";
import { Panel, Spinner, ErrorBanner, fmtPct } from "../components/ui";

const SIGNALS = ["technical", "volatility", "sentiment", "fundamentals"];

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

  if (settings.isLoading || !draft) return <Spinner />;
  const broker = settings.data!.broker;
  const watchlist = settings.data!.watchlist;

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
            Auto-trade recommendations during market hours
            <span className="text-slate-500"> (paper only; never places live orders)</span>
          </span>
        </label>
      </Panel>

      {/* Signal weights */}
      <Panel title="Signal Weights">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
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
        </p>
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
        </div>
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
        </div>
      </Panel>
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
