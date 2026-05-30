import { Panel } from "./ui";

// Single source of truth for the in-app limitations / disclosures, mirroring
// GUIDE.md so users see them without leaving the app.
const LIMITATIONS: { title: string; body: string }[] = [
  {
    title: "Paper trading only",
    body: "Orders, positions and balances run on an Alpaca paper account — no real money is at stake. This is an educational simulator, not financial advice.",
  },
  {
    title: "No guaranteed edge",
    body: "No screener reliably beats the market. Every recommendation is a hypothesis to validate in the backtester and on paper, not a signal to act on blindly.",
  },
  {
    title: "Daily-bar, swing horizon",
    body: "Signals are computed on daily bars — this is a swing / position tool, not an intraday or scalping system.",
  },
  {
    title: "Where ideas come from",
    body: "Recommendations scan the day's most-active US stocks (a rotating universe), not just your watchlist — your watchlist names are always included and marked with a ★. SELL/HOLD calls are signal-driven on this universe; they aren't tied to what you hold.",
  },
  {
    title: "One-click sizing",
    body: "The quick Buy sizes to your max-position cap, not the smaller volatility-targeted suggestion shown on the row. Use the Ticker panel to trade an exact size.",
  },
  {
    title: "Backtest scope",
    body: "Backtests use price-derived signals only (technical, volatility, momentum, regime). Sentiment & fundamentals are excluded to avoid look-ahead bias; survivorship and IEX data-coverage caveats also apply.",
  },
];

export function LimitationsPanel() {
  return (
    <Panel title="Important information & limitations">
      <ul className="space-y-3">
        {LIMITATIONS.map((l) => (
          <li key={l.title} className="flex gap-3">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
            <div>
              <div className="text-sm font-semibold text-slate-200">{l.title}</div>
              <div className="text-xs text-slate-400 leading-relaxed">{l.body}</div>
            </div>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export function DisclaimerFooter() {
  return (
    <div className="flex flex-col gap-1 text-xs text-slate-400">
      <p>
        <span className="font-semibold text-slate-300">StockSim</span> is a
        paper-trading simulator on Alpaca, built for education and research —{" "}
        <span className="text-slate-300">not financial advice</span>. No screener
        reliably beats the market; treat every signal as a hypothesis to test.
      </p>
      <p className="text-slate-500">
        Paper orders only · no real money at risk · past backtested performance
        does not predict future results.
      </p>
    </div>
  );
}
