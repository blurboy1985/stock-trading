import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type Recommendation } from "../api/client";
import { Panel, Spinner, ErrorBanner, fmtPct } from "../components/ui";
import { RegimeBanner } from "../components/RegimeBanner";
import { SectionGuide } from "../components/SectionGuide";

type LeaderboardMode = "momentum" | "composite";

export function Research() {
  const [mode, setMode] = useState<LeaderboardMode>("composite");

  const reco = useQuery({
    queryKey: ["reco"],
    queryFn: () => api.recommendations(false),
    refetchInterval: 60_000,
  });

  if (reco.isLoading) return <Spinner label="Loading research…" />;
  const data = reco.data;
  const recs = data?.recommendations ?? [];
  if (recs.length === 0) {
    return (
      <ErrorBanner message="No data yet. Configure IBKR/TWS settings and refresh recommendations." />
    );
  }

  const regime = data?.regime;

  // Sort based on selected mode
  const ranked = [...recs].sort((a, b) => {
    if (mode === "momentum") return momScore(b) - momScore(a);
    return b.score - a.score;
  });

  const lbTitle =
    mode === "momentum"
      ? "Relative-Strength Leaderboard"
      : "Composite Score Leaderboard";

  return (
    <div className="space-y-5">
      <RegimeBanner regime={regime} />
      <SectionGuide id="research" />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <Panel title="Market Regime Detail" className="lg:col-span-1">
          {regime ? (
            <div className="space-y-1.5 text-sm">
              <Row k="Label" v={regime.label.replace("_", "-")} />
              <Row k="Score" v={regime.score.toFixed(2)} />
              <Row k="Long multiplier" v={`×${regime.multiplier.toFixed(2)}`} />
              {Object.entries(regime.metrics).map(([k, v]) => (
                <Row key={k} k={k.replace(/_/g, " ")} v={fmtMetric(v)} />
              ))}
              <ul className="text-xs text-slate-400 list-disc pl-4 pt-2 space-y-0.5">
                {regime.reasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-slate-400 text-sm">Regime filter is off or idle.</p>
          )}
        </Panel>

        <Panel className="lg:col-span-2">
          <div className="flex items-center justify-between mb-3">
            <span className="text-slate-100 font-semibold text-sm">{lbTitle}</span>
            <div className="flex gap-1">
              {(
                [
                  ["composite", "Composite"],
                  ["momentum", "RS / Momentum"],
                ] as [LeaderboardMode, string][]
              ).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setMode(key)}
                  className={`text-xs font-medium px-3 py-1 rounded-full border transition-colors ${
                    mode === key
                      ? "bg-accent/15 border-accent/40 text-accent"
                      : "bg-panel border-edge text-slate-400 hover:bg-panel2"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <table className="w-full text-sm">
            <thead className="text-slate-400 text-xs uppercase">
              <tr className="text-left">
                <th className="py-2">#</th>
                <th>Symbol</th>
                {mode === "momentum" ? (
                  <>
                    <th>RS score</th>
                    <th>Momentum (raw)</th>
                  </>
                ) : (
                  <>
                    <th>Score</th>
                    <th>Conviction</th>
                  </>
                )}
                <th>Vol (ATR%)</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {ranked.map((r, i) => {
                const mom = r.breakdown?.momentum;
                const sortVal =
                  mode === "momentum" ? momScore(r) : r.score;
                return (
                  <tr key={r.symbol} className="border-t border-edge">
                    <td className="py-1.5 text-slate-500">{i + 1}</td>
                    <td className="font-semibold">
                      <Link to={`/ticker/${r.symbol}`} className="hover:text-accent">
                        {r.in_watchlist && (
                          <span className="text-accent mr-1" title="In your watchlist">
                            ★
                          </span>
                        )}
                        {r.symbol}
                      </Link>
                    </td>
                    {mode === "momentum" ? (
                      <>
                        <td
                          className={`font-mono ${
                            sortVal > 0 ? "text-buy" : sortVal < 0 ? "text-sell" : "text-slate-300"
                          }`}
                        >
                          {sortVal >= 0 ? "+" : ""}
                          {sortVal.toFixed(2)}
                        </td>
                        <td className="font-mono text-slate-400">
                          {numMetric(mom?.metrics?.raw)}
                        </td>
                      </>
                    ) : (
                      <>
                        <td
                          className={`font-mono ${
                            sortVal > 0 ? "text-buy" : sortVal < 0 ? "text-sell" : "text-slate-300"
                          }`}
                        >
                          {sortVal >= 0 ? "+" : ""}
                          {sortVal.toFixed(2)}
                        </td>
                        <td className="font-mono text-slate-400">
                          {r.conviction != null ? r.conviction.toFixed(2) : "—"}
                        </td>
                      </>
                    )}
                    <td className="font-mono text-slate-400">
                      {r.atr_pct != null ? fmtPct(r.atr_pct, 1) : "—"}
                    </td>
                    <td>
                      <span
                        className={
                          r.action === "BUY"
                            ? "text-buy"
                            : r.action === "SELL"
                            ? "text-sell"
                            : "text-slate-400"
                        }
                      >
                        {r.action}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Panel>
      </div>
    </div>
  );
}

function momScore(r: Recommendation): number {
  return r.breakdown?.momentum?.score ?? 0;
}

function numMetric(v: number | string | null | undefined): string {
  return typeof v === "number" ? v.toFixed(3) : "—";
}

function fmtMetric(v: number | string | boolean | null): string {
  if (v == null) return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(3);
  return String(v);
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3">
      <span className="text-slate-400 capitalize">{k}</span>
      <span className="font-mono text-slate-100">{v}</span>
    </div>
  );
}
