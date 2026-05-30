// Generic value heatmap: a labelled grid with per-cell color + text.
export function Heatmap({
  rowLabels,
  colLabels,
  values,
  colorFor,
  format,
  rowTitle,
  colTitle,
}: {
  rowLabels: (string | number)[];
  colLabels: (string | number)[];
  values: (number | null)[][];
  colorFor: (v: number | null) => string;
  format: (v: number | null) => string;
  rowTitle?: string;
  colTitle?: string;
}) {
  return (
    <div className="overflow-auto">
      <table className="border-separate border-spacing-1 text-xs">
        <thead>
          <tr>
            <th className="text-slate-500 font-normal text-right pr-2">
              {rowTitle ? `${rowTitle} \\ ${colTitle ?? ""}` : ""}
            </th>
            {colLabels.map((c) => (
              <th key={String(c)} className="text-slate-400 font-mono font-normal px-1">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rowLabels.map((r, ri) => (
            <tr key={String(r)}>
              <td className="text-slate-400 font-mono text-right pr-2">{r}</td>
              {colLabels.map((_, ci) => {
                const v = values[ri]?.[ci] ?? null;
                return (
                  <td
                    key={ci}
                    className={`w-14 h-10 text-center rounded font-mono text-[11px] ${colorFor(v)}`}
                    title={`${r} × ${colLabels[ci]}: ${format(v)}`}
                  >
                    {format(v)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Diverging green/red scale around zero — used for Sharpe / returns.
// NOTE: class strings must be static literals so Tailwind keeps them.
export function divergingColor(v: number | null, scale = 1.5): string {
  if (v == null || Number.isNaN(v)) return "bg-panel2 text-slate-600";
  const t = Math.max(-1, Math.min(1, v / scale));
  if (t > 0.66) return "text-buy bg-buy/40";
  if (t > 0.33) return "text-buy bg-buy/25";
  if (t > 0.05) return "text-buy bg-buy/15";
  if (t < -0.66) return "text-sell bg-sell/40";
  if (t < -0.33) return "text-sell bg-sell/25";
  if (t < -0.05) return "text-sell bg-sell/15";
  return "bg-panel2 text-slate-300";
}

// Correlation scale: 0 (uncorrelated) cool -> 1 (correlated) hot.
export function correlationColor(v: number | null): string {
  if (v == null || Number.isNaN(v)) return "bg-panel2 text-slate-600";
  if (v >= 0.999) return "bg-accent/40 text-slate-100";
  if (v >= 0.7) return "bg-sell/30 text-slate-100";
  if (v >= 0.4) return "bg-hold/30 text-slate-200";
  if (v >= 0.1) return "bg-buy/15 text-slate-200";
  return "bg-buy/30 text-slate-100";
}
