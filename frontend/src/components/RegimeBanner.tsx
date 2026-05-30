import type { Regime } from "../api/client";

const STYLES: Record<string, { box: string; dot: string; label: string }> = {
  risk_on: {
    box: "bg-buy/10 border-buy/40",
    dot: "bg-buy",
    label: "Risk-On",
  },
  neutral: {
    box: "bg-hold/10 border-hold/40",
    dot: "bg-hold",
    label: "Neutral",
  },
  risk_off: {
    box: "bg-sell/10 border-sell/40",
    dot: "bg-sell",
    label: "Risk-Off",
  },
};

// Market-regime banner: tells you whether it's a good time to be buying at all.
export function RegimeBanner({
  regime,
  compact = false,
}: {
  regime: Regime | null | undefined;
  compact?: boolean;
}) {
  if (!regime) return null;
  const s = STYLES[regime.label] ?? STYLES.neutral;
  const breadth = regime.metrics?.breadth_pct;
  const dampened = regime.multiplier < 1;

  return (
    <div className={`flex items-center gap-3 border rounded-xl px-4 py-2.5 ${s.box}`}>
      <span className={`h-2.5 w-2.5 rounded-full ${s.dot}`} />
      <div className="font-semibold text-sm">{s.label}</div>
      <div className="text-xs font-mono text-slate-300">
        score {regime.score >= 0 ? "+" : ""}
        {regime.score.toFixed(2)}
      </div>
      {dampened && (
        <span className="text-xs px-2 py-0.5 rounded bg-sell/15 text-sell border border-sell/40">
          longs ×{regime.multiplier.toFixed(2)}
        </span>
      )}
      {!compact && (
        <div className="flex items-center gap-3 text-xs text-slate-400 ml-auto">
          {typeof breadth === "number" && (
            <span>breadth {(breadth * 100).toFixed(0)}%</span>
          )}
          {regime.reasons.slice(0, 2).map((r, i) => (
            <span key={i} className="hidden md:inline">
              · {r}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
