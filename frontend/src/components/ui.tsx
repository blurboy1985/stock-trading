import type { ReactNode } from "react";

export const fmtUsd = (n: number | null | undefined) =>
  n == null ? "—" : n.toLocaleString("en-US", { style: "currency", currency: "USD" });

export const fmtPct = (n: number | null | undefined, digits = 2) =>
  n == null ? "—" : `${(n * 100).toFixed(digits)}%`;

export const fmtNum = (n: number | null | undefined, digits = 2) =>
  n == null ? "—" : n.toFixed(digits);

export const fmtSignedUsd = (n: number | null | undefined) =>
  n == null ? "—" : `${n >= 0 ? "+" : "-"}${fmtUsd(Math.abs(n))}`;

export const fmtSignedPct = (n: number | null | undefined, digits = 2) =>
  n == null ? "—" : `${n >= 0 ? "+" : "-"}${(Math.abs(n) * 100).toFixed(digits)}%`;

export function Panel({
  title,
  children,
  right,
  className = "",
}: {
  title?: string;
  children: ReactNode;
  right?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`bg-panel border border-edge rounded-2xl p-5 shadow-card ${className}`}>
      {title && (
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-[11px] font-bold text-slate-400 uppercase tracking-[0.1em]">
            {title}
          </h3>
          {right}
        </div>
      )}
      {children}
    </div>
  );
}

export function Stat({
  label,
  value,
  sub,
  tone = "neutral",
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "neutral" | "up" | "down";
}) {
  const toneCls =
    tone === "up" ? "text-buy" : tone === "down" ? "text-sell" : "text-slate-100";
  return (
    <div className="bg-panel border border-edge rounded-2xl px-4 py-3.5 shadow-card">
      <div className="text-xs font-medium text-slate-400">{label}</div>
      <div className={`text-2xl font-extrabold tracking-tight ${toneCls}`}>{value}</div>
      {sub && <div className="text-xs text-slate-400 mt-0.5">{sub}</div>}
    </div>
  );
}

export function ActionBadge({ action }: { action: string }) {
  const map: Record<string, string> = {
    BUY: "bg-buy/15 text-buy border-buy/40",
    SELL: "bg-sell/15 text-sell border-sell/40",
    HOLD: "bg-hold/15 text-slate-300 border-hold/40",
  };
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded border ${map[action] ?? map.HOLD}`}>
      {action}
    </span>
  );
}

export function ScoreBar({ score }: { score: number }) {
  // Map [-1,1] to a centered bar.
  const pct = Math.min(100, Math.abs(score) * 100);
  const color = score > 0.05 ? "bg-buy" : score < -0.05 ? "bg-sell" : "bg-hold";
  return (
    <div className="relative h-2 w-full bg-panel2 rounded overflow-hidden">
      <div className="absolute left-1/2 top-0 h-full w-px bg-edge" />
      <div
        className={`absolute top-0 h-full ${color}`}
        style={
          score >= 0
            ? { left: "50%", width: `${pct / 2}%` }
            : { right: "50%", width: `${pct / 2}%` }
        }
      />
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-slate-400 text-sm py-8 justify-center">
      <div className="h-4 w-4 border-2 border-accent/30 border-t-accent rounded-full animate-spin" />
      {label ?? "Loading…"}
    </div>
  );
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="bg-sell/10 border border-sell/40 text-sell rounded-lg px-4 py-3 text-sm">
      {message}
    </div>
  );
}
