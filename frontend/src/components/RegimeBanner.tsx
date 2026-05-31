import { useState } from "react";
import type { Regime, RegimeComponent } from "../api/client";

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

// Risk-on / risk-off is a pure, price-derived read of the broad market. These
// labels explain what each scored component is actually measuring.
const COMPONENT_INFO: Record<string, { label: string; about: string }> = {
  trend: {
    label: "Long-term trend",
    about:
      "Benchmark above/below its ~200d SMA — the single biggest tell. ±0.40.",
  },
  ma_cross: {
    label: "50d vs long SMA",
    about: "Golden cross (50d over long SMA) vs death cross. ±0.20.",
  },
  slope: {
    label: "Trend slope",
    about: "Slope of the long SMA over ~20 bars; a rising trend is risk-on. ±0.20.",
  },
  drawdown: {
    label: "Drawdown",
    about: "Penalty when the benchmark is ≥10% off its trailing high. −0.20.",
  },
  breadth: {
    label: "Breadth",
    about:
      "Share of the universe above its own trend — confirms the average stock is participating, not just the index. ±0.20.",
  },
};

// Market-regime banner: tells you whether it's a good time to be buying at all,
// and (expanded) exactly how that risk-on/off score was assembled.
export function RegimeBanner({
  regime,
  compact = false,
}: {
  regime: Regime | null | undefined;
  compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  if (!regime) return null;
  const s = STYLES[regime.label] ?? STYLES.neutral;
  const breadth = regime.metrics?.breadth_pct;
  const dampened = regime.multiplier < 1;
  const components = regime.components ?? [];
  const expandable = !compact && components.length > 0;

  return (
    <div className={`border rounded-xl ${s.box}`}>
      <div className="flex items-center gap-3 px-4 py-2.5">
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
            {!open &&
              regime.reasons.slice(0, 2).map((r, i) => (
                <span key={i} className="hidden md:inline">
                  · {r}
                </span>
              ))}
            {expandable && (
              <button
                onClick={() => setOpen((v) => !v)}
                className="text-slate-400 hover:text-slate-200 text-xs"
                title="How the regime score is computed"
              >
                {open ? "▲ hide" : "▼ how"}
              </button>
            )}
          </div>
        )}
      </div>

      {open && expandable && (
        <RegimeBreakdown regime={regime} components={components} />
      )}
    </div>
  );
}

const signed = (n: number, d = 2) => `${n >= 0 ? "+" : ""}${n.toFixed(d)}`;

/** Component-by-component breakdown of how the risk-on/off score was built. */
function RegimeBreakdown({
  regime,
  components,
}: {
  regime: Regime;
  components: RegimeComponent[];
}) {
  const maxAbs = Math.max(0.2, ...components.map((c) => Math.abs(c.contribution)));
  // The label bands (risk-on ≥ +0.20, risk-off ≤ −0.20) live in regime.py.
  return (
    <div className="px-4 pb-4 pt-1 border-t border-edge/60 space-y-3">
      <p className="text-xs text-slate-500">
        A pure, price-derived read of the broad market ({regime.metrics?.long_window
          ? `${regime.metrics.long_window}d`
          : "long"}{" "}
        trend on the benchmark). Each component adds a signed tilt; they sum to the
        regime score, which gates new longs (risk-off throttles buys toward ×0.40;
        sells are never dampened).
      </p>

      <div className="space-y-1.5">
        {components.map((c) => {
          const info = COMPONENT_INFO[c.name];
          return (
            <div key={c.name} className="flex items-center gap-2 text-xs">
              <div className="w-28 text-slate-300" title={info?.about}>
                {info?.label ?? c.name}
              </div>
              <div className="flex-1 relative h-4 bg-panel rounded overflow-hidden min-w-[80px]">
                <div className="absolute left-1/2 top-0 h-full w-px bg-edge" />
                <div
                  className={`absolute top-0 h-full ${
                    c.contribution >= 0 ? "bg-buy/60" : "bg-sell/60"
                  }`}
                  style={
                    c.contribution >= 0
                      ? {
                          left: "50%",
                          width: `${(Math.abs(c.contribution) / maxAbs) * 50}%`,
                        }
                      : {
                          right: "50%",
                          width: `${(Math.abs(c.contribution) / maxAbs) * 50}%`,
                        }
                  }
                />
              </div>
              <div
                className={`w-12 text-right font-mono ${
                  c.contribution > 0
                    ? "text-buy"
                    : c.contribution < 0
                      ? "text-sell"
                      : "text-slate-400"
                }`}
              >
                {signed(c.contribution)}
              </div>
            </div>
          );
        })}
      </div>

      {/* per-component detail lines, so the bars above have their "why". */}
      <ul className="text-[11px] text-slate-500 list-disc pl-5 space-y-0.5">
        {components.map((c) => (
          <li key={c.name}>{c.detail}</li>
        ))}
      </ul>

      <div className="flex items-center justify-between pt-2 border-t border-edge/60 text-xs">
        <span className="text-slate-400">
          Sum → regime score · risk-on ≥ +0.20, risk-off ≤ −0.20
        </span>
        <span
          className={`font-mono font-bold ${
            regime.score >= 0.2
              ? "text-buy"
              : regime.score <= -0.2
                ? "text-sell"
                : "text-hold"
          }`}
        >
          {signed(regime.score)}
        </span>
      </div>
    </div>
  );
}
