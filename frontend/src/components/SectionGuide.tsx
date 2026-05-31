import { useState, type ReactNode } from "react";

// ─────────────────────────────────────────────────────────────────────────────
// Per-section guide: a lightweight "How this page works" explainer that sits at
// the top of each main view. It tells a newcomer what the section is for and how
// to use it, in plain language, referencing only controls that actually exist.
//
// All copy lives in the GUIDES registry below so every page stays a one-liner:
//   <SectionGuide id="dashboard" />
//
// It opens by default the first time a user lands on a page (so the guidance is
// actually seen) and remembers a collapse per-page in localStorage, so once you
// know a screen you can keep it tucked away. The broker's buy/sell walkthrough
// (TradeWalkthrough) is the cross-cutting tour; these are the per-screen primers.
// ─────────────────────────────────────────────────────────────────────────────

const b = (t: string) => <strong className="text-slate-200 font-semibold">{t}</strong>;

type Guide = {
  /** Heading shown beside the toggle. Omit on pages that already have their own. */
  title?: string;
  /** One-paragraph "what this section is for". */
  what: ReactNode;
  /** "How to use it" points. */
  how: ReactNode[];
  /** Optional closing tip / caveat. */
  tip?: ReactNode;
};

const GUIDES: Record<string, Guide> = {
  dashboard: {
    title: "Dashboard",
    what: (
      <>
        Your live account command center. Everything here is read in real time
        from your Alpaca paper account — the same balances, positions and orders
        you'd see on alpaca.markets — and refreshes on its own every few seconds.
      </>
    ),
    how: [
      <>The top cards show {b("Portfolio Value, Equity, Cash and Buying Power")}, with today's profit or loss on the portfolio card.</>,
      <>{b("Positions")} lists what you hold with live P&L. The {b("Close")} button on the right is a deliberate two-step: it arms to {b("Confirm")} on the first click, then sells the whole position at market on the second.</>,
      <>{b("Open Orders")} shows working (unfilled) orders — hit {b("Cancel")} to pull one. {b("Activity")} is your recent fills and account events.</>,
      <>{b("Top Signals")} is a shortcut to today's strongest buys; click any symbol to open its chart and trade panel.</>,
    ],
    tip: <>The badge by “Account Overview” (and top-right of every page) tells you whether you're in {b("PAPER")} or {b("LIVE")} mode — it should say PAPER.</>,
  },
  recommendations: {
    title: "Recommendations",
    what: (
      <>
        Your daily ranking. We scan a universe of US stocks plus your watchlist,
        score each on the price signals that actually backtest (technical,
        volatility, momentum), and sort by a risk-adjusted score. News sentiment
        and fundamentals don't pad the score — by default they only veto a clearly
        negative buy.
      </>
    ),
    how: [
      <>Read each row left-to-right: {b("BUY / SELL / HOLD")} badge → score → {b("conv")} (conviction) → {b("vol")} (volatility) → {b("size")} (suggested weight) → price.</>,
      <>Filter with the {b("All / ★ Watchlist / Buys / Sells")} chips. A ★ marks a watchlist name; a ⚠ thin marker flags an illiquid one.</>,
      <>Click the {b("▼")} on any row to expand the full thesis — how the score was built, how big a position to take, and per-signal notes (tap {b("ⓘ")} on a note for its definition and live numbers).</>,
      <>The green {b("Buy")} button is a one-click paper order (sized to your max-position cap). For an exact size, click the symbol and use the Ticker trade panel. {b("Refresh now")} re-scores against the latest prices.</>,
    ],
    tip: <>A buy can be suppressed near earnings, in a risk-off regime, when a sector is already full, or on a negative veto — the expanded thesis tells you which.</>,
  },
  automation: {
    title: "Automation",
    what: (
      <>
        Hands-off idea generation with a human gate. When auto-propose is on,
        StockSim scans the market every 15 minutes during market hours and drafts
        trades from the latest signals. Nothing is ever placed until you confirm
        it.
      </>
    ),
    how: [
      <>Each card shows the proposed {b("side, share count, estimated cost, % of equity")} and a one-line rationale.</>,
      <>{b("Confirm")} places that paper order; {b("Reject")} dismisses it; {b("Confirm all")} clears the whole queue at once.</>,
      <>A proposal marked {b("⚠ Can't place")} failed a risk check (e.g. exposure or sector cap) and can't be confirmed — that's the guardrail doing its job.</>,
      <>The number badge on the Automation tab in the top nav counts proposals waiting on you.</>,
    ],
    tip: <>Turn auto-propose on or off in {b("Settings → Automation")}. Like everything else, it's paper-only.</>,
  },
  research: {
    title: "Research",
    what: (
      <>
        The macro and relative-strength view behind the rankings. It explains the
        current market regime and shows which names are leading the pack on
        momentum.
      </>
    ),
    how: [
      <>{b("Market Regime Detail")} breaks down the broad-market filter: its label (risk-on / risk-off), score, the long multiplier it applies, and the metrics and reasons behind it.</>,
      <>{b("Relative-Strength Leaderboard")} ranks the scanned universe by momentum — the leaders the strategy favors. Columns show RS score, raw momentum, volatility (ATR%) and the current action.</>,
      <>Click any symbol to open its chart, news and trade panel.</>,
    ],
    tip: <>Regime matters: in a risk-off tape longs are dampened or blocked outright, so a thin leaderboard is itself a signal to sit on your hands.</>,
  },
  backtest: {
    title: "Backtest",
    what: (
      <>
        Prove a strategy before you trust it. This replays the scoring engine over
        historical prices for the symbols you choose and reports how it would have
        performed — using price-derived signals only (sentiment & fundamentals are
        excluded to avoid look-ahead), so what you test matches the live score.
      </>
    ),
    how: [
      <>Set {b("Symbols")}, a date range and exits, then {b("Run backtest")}. {b("ATR stop ×")} places a volatility-scaled stop, {b("ATR trail ×")} ratchets a trailing stop so winners run, and {b("Min agreement")} demands multi-signal confluence to enter.</>,
      <>Read the metric cards — {b("Total Return vs Buy & Hold, Sharpe, Max Drawdown, Win Rate, Profit Factor")} — and the equity curve (blue = strategy, grey = buy & hold).</>,
      <>{b("Per-Signal P&L Attribution")} shows which signals made or lost money; the trades table lists every entry, exit and why it closed.</>,
      <>Use {b("Walk-forward")} (picks the threshold on past data, trades it on unseen data) and {b("Parameter sweep")} (maps performance across settings) to check the edge is real, not overfit.</>,
    ],
    tip: <>A broad green plateau in the sweep is robust; a lone bright cell is probably overfit. Past backtested performance does not predict future results.</>,
  },
  history: {
    title: "History",
    what: (
      <>
        Your realized track record, read live from Alpaca. It charts account
        equity over time and lists the orders that actually filled.
      </>
    ),
    how: [
      <>Switch the {b("1M / 3M / 1Y")} range to reframe the equity curve and the period P&L cards.</>,
      <>{b("Trade History")} lists filled orders with date, side, quantity and type.</>,
      <>Click any symbol to revisit its chart.</>,
    ],
    tip: <>P&L here is Alpaca's account equity change (realized + unrealized) over the period — the same numbers you'd see on the Alpaca site.</>,
  },
  settings: {
    title: "Settings",
    what: (
      <>
        Where you tune how StockSim scans, scores, sizes and protects every trade.
        Changes apply to live scoring and — for the price-derived knobs — to
        backtests too. Hit {b("Save settings")} to apply.
      </>
    ),
    how: [
      <>{b("Broker & Safety")} confirms your Alpaca credentials and that you're locked to paper; {b("Automation")} toggles auto-propose.</>,
      <>{b("Universe")} picks what gets scanned — the stable {b("Core liquid set")} is best for swing relative-strength. {b("Signal Weights")} and {b("Sentiment & Fundamentals")} shape the score (veto-only mode keeps sentiment/fundamentals out of the score and uses them only to block bad buys).</>,
      <>{b("Quant Controls")} and {b("Risk Limits")} hold the guardrails: regime gate, earnings blackout, sector cap, min agreement, position/exposure caps and ATR stops.</>,
      <>{b("Watchlist")} manages your starred symbols (auto-synced to Alpaca).</>,
    ],
    tip: <>New here? The “Getting Started” panel further down replays the full broker's walkthrough of finding, buying and selling a name.</>,
  },
  ticker: {
    // No title — the page already shows the symbol as a big heading.
    what: (
      <>
        The single-name view: a full price chart, a live quote, the latest news,
        and a panel to place a paper trade in this exact symbol.
      </>
    ),
    how: [
      <>Switch the chart range with the {b("1M … ALL")} buttons; the percentage beside the header is the return over whatever range you're viewing.</>,
      <>In {b("Trade (paper)")}, enter a {b("Qty")} and press {b("Buy")} or {b("Sell")} — leave Qty blank to auto-size to your risk settings. Every order is risk-checked before it's sent.</>,
      <>{b("Recent News")} is the headline flow behind the sentiment read — scan it for anything that contradicts the signal before you commit.</>,
    ],
    tip: <>Selling here can trim part of a position (enter a smaller Qty); the Dashboard's Close button always exits the whole thing.</>,
  },
};

export function SectionGuide({ id }: { id: keyof typeof GUIDES }) {
  const g = GUIDES[id];
  const key = `stocksim_secguide_${id}`;
  const [open, setOpen] = useState(() => localStorage.getItem(key) !== "0");

  if (!g) return null;

  const toggle = () =>
    setOpen((v) => {
      const next = !v;
      localStorage.setItem(key, next ? "1" : "0");
      return next;
    });

  return (
    <div>
      <div className={`flex items-center gap-3 ${g.title ? "justify-between" : "justify-end"}`}>
        {g.title && <h2 className="text-lg font-bold text-slate-100">{g.title}</h2>}
        <button
          onClick={toggle}
          aria-expanded={open}
          className="shrink-0 text-xs font-semibold px-3 py-1.5 rounded-full border border-accent/40 text-accent bg-accent/10 hover:bg-accent/20 transition-colors"
        >
          {open ? "Hide guide ▴" : "How this page works ▾"}
        </button>
      </div>

      {open && (
        <div className="mt-3 bg-panel border border-edge rounded-2xl p-5 shadow-card">
          <p className="text-sm text-slate-300 leading-relaxed">{g.what}</p>
          <ul className="mt-3 space-y-2">
            {g.how.map((h, i) => (
              <li key={i} className="flex gap-2.5 text-sm text-slate-400 leading-relaxed">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                <span>{h}</span>
              </li>
            ))}
          </ul>
          {g.tip && (
            <p className="mt-4 text-xs text-slate-500 border-t border-edge pt-3 leading-relaxed">
              💡 {g.tip}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
