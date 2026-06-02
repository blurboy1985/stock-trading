import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

// ─────────────────────────────────────────────────────────────────────────────
// Broker's walkthrough: an in-app guided tour, written in the voice of a senior
// broker, that walks the user through the app's real buy/sell features. It only
// references controls that actually exist (Recommendations row Buy, the Ticker
// "Trade (paper)" panel, the Dashboard Open Positions Sell→Confirm, and Open
// Orders Cancel) so the guidance never drifts from the UI. It also explains the
// swing-trading mechanics that shape what gets recommended and how exits work:
// the price-only score with sentiment/fundamentals as a veto, the earnings /
// regime / sector guardrails, and the ATR + trailing-stop exits (all tunable in
// Settings and testable on the Backtest tab).
//
// Trigger it from anywhere with `openTradeGuide()`; it also auto-opens on the
// first visit (tracked in localStorage).
// ─────────────────────────────────────────────────────────────────────────────

const SEEN_KEY = "stocksim_guide_seen";
const OPEN_EVENT = "stocksim:open-trade-guide";

/** Open the walkthrough from anywhere (header button, Settings, etc.). */
export function openTradeGuide() {
  window.dispatchEvent(new Event(OPEN_EVENT));
}

type Step = {
  badge: string;
  title: string;
  /** Broker-voiced explanation. */
  body: string;
  /** Concrete on-screen cues — exact labels the user will see. */
  cues?: string[];
  /** If set, the step offers a button that navigates there. */
  route?: { to: string; label: string };
};

const STEPS: Step[] = [
  {
    badge: "Welcome",
    title: "I'll walk you through placing a trade",
    body: "Think of me as your broker. In the next minute I'll show you exactly where to find an idea, how to read it, how to buy it, and how to sell or trim what's already in your book. Everything here defaults to IBKR paper mode — so it's the perfect place to build the habit before any real capital is involved.",
    cues: [
      "Your live status sits top-right of the header: a green ● PAPER badge means no real money is at stake.",
      "Use Back / Next below to move at your own pace, or jump straight to a screen with the blue button.",
    ],
  },
  {
    badge: "1 · Find an idea",
    title: "Start on Recommendations",
    body: "This is your morning ranking. We scan a universe of US stocks — plus every name on your watchlist — and score each on the price-derived signals that actually backtest: technical, volatility and momentum. News sentiment and fundamentals don't pad the score; by default they sit on the sidelines as a safety veto (more on that next). Everything is then sorted by a risk-adjusted score: green BUY badges are candidates to add, red SELL badges are names to lighten or avoid.",
    cues: [
      "A ★ marks your watchlist names; use the All / ★ Watchlist / Buys / Sells chips to filter.",
      "Read the row left-to-right: BUY/SELL/HOLD badge → score → conv (conviction) → vol → size (suggested weight) → price.",
      "Hit “Refresh now” to re-score against the latest prices.",
      "A ⚠ thin marker warns the name is illiquid — size down or skip.",
      "Tip: in Settings → Universe you can scan the “Core liquid set” instead of the day's most-actives — a stable pond that makes relative-strength ranking far better for swing trading.",
    ],
    route: { to: "/recommendations", label: "Open Recommendations" },
  },
  {
    badge: "2 · Read the thesis",
    title: "Never buy a number you don't understand",
    body: "Before committing capital, open the reasoning. Click the ▼ chevron on the right of any row to expand it. You'll see the plain-English “Why this score”, the agreement across signals, the suggested size, and a per-signal breakdown so you can see what's actually driving the call. Sentiment and fundamentals show up here as context — and if either turns clearly negative, they can veto an otherwise-green buy.",
    cues: [
      "Expand the row with the ▼ on the far right.",
      "Low agreement or a single dominant signal = a thinner thesis; treat it with more caution.",
      "“regime dampened” means the broad-market filter is throttling longs in a risk-off tape; a hard “regime gate” can block new longs outright when the tape is clearly risk-off.",
      "A buy can also be suppressed near earnings, when a sector is already full, or on a negative sentiment/fundamentals veto — the note tells you which.",
    ],
    route: { to: "/recommendations", label: "Open Recommendations" },
  },
  {
    badge: "3 · Do the homework",
    title: "Check the chart and the tape",
    body: "Click any ticker symbol — on a recommendation, a position, or a top signal — to open its page. You get a 250-day price chart and the latest headlines. A good entry lines up with the trend and isn't fighting fresh bad news.",
    cues: [
      "Click the bold symbol (e.g. NVDA) anywhere it appears to open the Ticker page.",
      "Scan “Recent News” for anything that contradicts the signal.",
    ],
  },
  {
    badge: "4 · Place the buy",
    title: "Two ways to buy — pick your size",
    body: "You have a quick path and a precise path. On a Recommendations row, the green “Buy” button is one-click — but note it sizes to your max-position cap, not the smaller volatility-targeted suggestion on the row. For an exact size, open the ticker and use the “Trade (paper)” panel: type a quantity (or leave it blank to auto-size), then press Buy.",
    cues: [
      "Quick buy: green “Buy” on the Recommendations row (caps at max position).",
      "Exact buy: Ticker → “Trade (paper)” → enter Qty → Buy. Blank Qty = auto-size.",
      "Every order is risk-checked before it's sent: position size, total exposure, per-sector cap, earnings blackout, and the protective stop are all applied automatically.",
      "If a guardrail blocks the order you'll see why — it's protecting you, not malfunctioning.",
      "You'll see “Order submitted ✓” on success.",
    ],
  },
  {
    badge: "5 · Let it work",
    title: "Your exit is half-automatic",
    body: "When you buy, a protective stop rides along with the position so a single bad name can't run away from you. By default it's sized to the stock's own volatility (an ATR-based stop, not a flat percentage), so a quiet name gets a tight stop and a wild one gets room to breathe. You can also let the stop trail upward as the trade works — a chandelier trailing stop that locks in gains while letting winners run, instead of capping them at a fixed take-profit.",
    cues: [
      "The stop is attached at entry — you don't have to place it manually.",
      "Tune it in Settings → Risk Limits: “ATR stop multiple” for the volatility-scaled stop, and the Backtest tab's “ATR trail ×” to test a trailing exit.",
      "You can still exit by hand any time from the Dashboard (next step) — the stop is a backstop, not a cage.",
    ],
  },
  {
    badge: "6 · Manage your book",
    title: "Sell or close from the Dashboard",
    body: "Your open positions live on the Dashboard. To exit, find the position under “Open Positions” and use the Close column on the right. It's a deliberate two-step: the button reads “Sell”, and after you click it arms to “Confirm” — click again to sell the whole position at market. That second click is your safety catch against fat-fingering an exit.",
    cues: [
      "Dashboard → Open Positions → Close column → “Sell”, then “Confirm”.",
      "Watch the Unrealized P&L column (green = up, red = down) to decide what to trim.",
      "To sell only part of a position, open the ticker and enter a smaller Qty on the Trade panel instead.",
    ],
    route: { to: "/", label: "Go to Dashboard" },
  },
  {
    badge: "7 · Work your orders",
    title: "Cancel anything still working",
    body: "Orders that haven't filled show under “Open Orders” on the Dashboard, with their side, quantity, type and status. If a trade no longer makes sense, hit Cancel on its row — it drops from the list immediately and reconciles on the next refresh.",
    cues: [
      "Dashboard → Open Orders → Cancel.",
      "“filled” shows how much of the order has already executed.",
    ],
    route: { to: "/", label: "Go to Dashboard" },
  },
  {
    badge: "Before you risk anything",
    title: "Validate first — no screener beats the market",
    body: "My honest broker's advice: treat every recommendation as a hypothesis, not a sure thing. Take a name you like to the Backtest tab and see how the strategy behaved historically before you lean on it — and use it to settle your own settings, like whether an ATR trailing stop actually beats a fixed take-profit on the names you trade. This whole app is paper-only by design so you can build conviction safely. Trade the process, not the tip.",
    cues: [
      "Backtests replay price-derived signals only (sentiment & fundamentals are excluded to avoid look-ahead), so what you test is what drives the live score.",
      "Try “ATR trail ×” and “Min agreement” in the config, then Walk-forward / Parameter sweep to check the edge holds out-of-sample.",
      "All these knobs — universe, veto mode, ATR stops, regime and sector gates — live in Settings once you've found what you like.",
      "Past backtested performance does not predict future results.",
    ],
    route: { to: "/backtest", label: "Open Backtest" },
  },
];

export function TradeWalkthrough() {
  const [open, setOpen] = useState(false);
  const [i, setI] = useState(0);
  const navigate = useNavigate();

  // Open on demand only (header / Settings). Auto-opening this modal on first
  // visit made normal pages such as History look broken because the walkthrough
  // blocked all interaction until dismissed.
  useEffect(() => {
    const onOpen = () => {
      setI(0);
      setOpen(true);
    };
    window.addEventListener(OPEN_EVENT, onOpen);
    return () => window.removeEventListener(OPEN_EVENT, onOpen);
  }, []);

  // Escape to close.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      if (e.key === "ArrowRight") setI((v) => Math.min(STEPS.length - 1, v + 1));
      if (e.key === "ArrowLeft") setI((v) => Math.max(0, v - 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function close() {
    setOpen(false);
    localStorage.setItem(SEEN_KEY, "1");
  }

  if (!open) return null;
  const step = STEPS[i];
  const isLast = i === STEPS.length - 1;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-slate-100/70 backdrop-blur-sm"
        onClick={close}
      />
      <div className="relative w-full max-w-lg bg-panel border border-edge rounded-2xl shadow-cardhover overflow-hidden">
        {/* Progress bar */}
        <div className="h-1 w-full bg-panel2">
          <div
            className="h-full bg-accent transition-all duration-300"
            style={{ width: `${((i + 1) / STEPS.length) * 100}%` }}
          />
        </div>

        <div className="p-6">
          <div className="flex items-center justify-between mb-3">
            <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-accent bg-accent/10 border border-accent/20 rounded-full px-2.5 py-1">
              {step.badge}
            </span>
            <button
              onClick={close}
              className="text-slate-400 hover:text-slate-200 text-sm"
              aria-label="Close walkthrough"
            >
              Skip ✕
            </button>
          </div>

          <h2 className="text-xl font-bold text-slate-100 mb-2">{step.title}</h2>
          <p className="text-sm text-slate-300 leading-relaxed">{step.body}</p>

          {step.cues && (
            <ul className="mt-4 space-y-2">
              {step.cues.map((c, k) => (
                <li key={k} className="flex gap-2.5 text-xs text-slate-400 leading-relaxed">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                  <span>{c}</span>
                </li>
              ))}
            </ul>
          )}

          {step.route && (
            <button
              onClick={() => {
                navigate(step.route!.to);
                close();
              }}
              className="mt-5 w-full bg-accent text-white text-sm font-medium py-2.5 rounded-lg hover:bg-accent/85 transition-colors"
            >
              {step.route.label} →
            </button>
          )}
        </div>

        {/* Footer nav */}
        <div className="flex items-center justify-between gap-3 px-6 py-4 border-t border-edge bg-panel2/50">
          <div className="flex gap-1.5">
            {STEPS.map((_, k) => (
              <button
                key={k}
                onClick={() => setI(k)}
                aria-label={`Go to step ${k + 1}`}
                className={`h-1.5 rounded-full transition-all ${
                  k === i ? "w-5 bg-accent" : "w-1.5 bg-slate-600 hover:bg-slate-500"
                }`}
              />
            ))}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setI((v) => Math.max(0, v - 1))}
              disabled={i === 0}
              className="text-sm px-3 py-1.5 rounded-lg border border-edge text-slate-300 hover:bg-panel2 disabled:opacity-40"
            >
              Back
            </button>
            {isLast ? (
              <button
                onClick={close}
                className="text-sm px-4 py-1.5 rounded-lg bg-buy/15 border border-buy/40 text-buy hover:bg-buy/25"
              >
                Got it
              </button>
            ) : (
              <button
                onClick={() => setI((v) => Math.min(STEPS.length - 1, v + 1))}
                className="text-sm px-4 py-1.5 rounded-lg bg-accent/15 border border-accent/40 text-accent hover:bg-accent/25"
              >
                Next
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
