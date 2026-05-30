# 📈 StockSim — Daily Use Guide

A practical, step-by-step walkthrough of how to run StockSim for day-to-day
stock research and (paper) trading. Read the honesty notes — they tell you what
the tool *does* and, just as importantly, what it does **not** do.

> **What this tool is.** A multi-signal **swing/position** screener and
> **paper-trading** cockpit on daily bars. It ranks a watchlist, explains *why*,
> sizes positions by risk, and lets you validate ideas in a backtester before
> risking anything. It is **not** an intraday/scalping system, and it is not
> financial advice. No screener reliably beats the market — treat every
> recommendation as a hypothesis.

---

## 0. One-time setup

1. **Get free Alpaca paper credentials** at <https://alpaca.markets> → *Paper
   Trading* dashboard → generate an API key + secret.
2. **Backend** — from `backend/`:
   ```powershell
   python -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   copy .env.example .env     # paste APCA_API_KEY_ID / APCA_API_SECRET_KEY
   ```
3. **Frontend** — from `frontend/`: `npm install`.
4. **Launch both** — from the repo root: `./dev.ps1` (opens backend on `:8000`,
   frontend on `:5173`). Open <http://localhost:5173>.

The header badge shows **● PAPER** (green) or **● LIVE** (red) so you always
know which money is at stake. It will read PAPER unless you have deliberately
switched to live keys (see §7).

> Runs without credentials too — pages show a clear "not configured" message and
> point you to Settings.

---

## 1. Configure once, then leave it (Settings tab)

Do this before your first session; revisit only when your strategy changes.

- **Watchlist** — add/remove the tickers you want ranked (default is 10 liquid
  large-caps + SPY). This *is* your universe; the engine only scores these.
  Changes **auto-sync to a "StockSim" watchlist on your Alpaca account** (and a
  **Sync to Alpaca** button forces it), so you can see the same list when you log
  in to the Alpaca site.
- **Signal weights** — how much each family counts toward the composite score
  (technical / volatility / momentum / sentiment / fundamentals). Auto-normalized
  across active signals. Leave at defaults until a backtest tells you otherwise.
- **Sentiment & fundamentals** — engine = *Lexicon* (offline, instant, default)
  or *Claude* (uses your Claude Code subscription; falls back to lexicon on any
  error). News half-life and finance-lexicon weight tune the sentiment signal;
  "score valuation relative to sector peers" makes fundamentals compare each
  name's P/E etc. against the live-universe sector median.
- **Quant controls** — regime filter (throttles longs in a risk-off tape),
  volatility-targeted sizing, benchmark (SPY), target risk per position, and the
  liquidity floors (min $-volume, min price).
- **Risk limits** — max position %, max total exposure %, stop-loss %, take-profit
  %. **These are enforced on every order** (§4). Set them to what you can live
  with; they are your seatbelt.

Click **Save settings**. Changes take effect on the next recommendation refresh —
no restart needed.

---

## 2. Start your session — read the regime first (Dashboard)

Open the **Dashboard**:

- **Equity / Today's P&L / Cash / Buying Power** at the top.
- **Regime banner** — risk-on / neutral / risk-off for the broad market. In a
  risk-off tape the engine already dampens long scores; treat new BUYs with extra
  skepticism.
- **Open Positions** — your paper book with unrealized P&L. Click a symbol to
  open its Ticker page, or hit **Sell → Confirm** on the row to close the whole
  position at market.
- **Open Orders** — any working/pending orders (including bracket children), each
  with a **Cancel** button.
- **Top Signals** — a shortcut to the strongest current BUYs.

The dashboard auto-refreshes (positions and orders every ~10s, signals every ~30s).

---

## 3. Review the ranked ideas (Recommendations tab)

This is the core screen. The watchlist is ranked by a **risk-adjusted score**
(conviction-weighted, volatility-penalized) — not raw score — so the top of the
list is "best reward per unit of risk," not just "highest signal."

Each row shows: **action** (BUY/SELL/HOLD), a score bar, **score**, **conv**
(conviction = magnitude × agreement across signals), **vol** (ATR%), **size**
(suggested portfolio weight), and price. A **⚠ thin** flag means the name failed
the liquidity floor and any BUY was suppressed to HOLD.

**Expand a row** (▼) to see the part that matters: the **per-signal breakdown**
(each family's score + weight), the **plain-English reasons** ("news sentiment
positive…", "P/E below sector median…", "MACD cross up…"), the **agreement**
(how unanimous the signals are), the **suggested size/qty**, and any **regime
dampening** applied.

> **Broker's note — don't trade the headline number.** A BUY backed by one lone
> signal at low agreement is far weaker than the same score with four signals
> agreeing. Read the breakdown and reasons every time. The score is a starting
> point for *your* judgment, not a verdict.

Hit **Refresh now** to recompute on demand (works after hours using the latest
available daily bars). The background scheduler also refreshes every 15 minutes
during market hours.

---

## 4. Dig into a single name (Ticker page)

Click any symbol (from Dashboard, Recommendations, or Research) to open
`/ticker/SYMBOL`:

- **250-day price chart** and a **live quote**.
- **Recent news headlines** (the raw stories behind the sentiment signal).
- **Trade panel (paper)** — Buy / Sell with an optional quantity. Leave qty
  **blank to auto-size**; enter a number to trade an exact size.

Every order — here, the one-click Buy on Recommendations, or the auto-trader —
passes the **single risk chokepoint** (`services/risk.py`) before it reaches
Alpaca:

- **Sell** only what you hold (no shorting in the simulator).
- **Buy** is rejected if it exceeds buying power, the **per-position cap**, or the
  **total-exposure cap**.
- Approved **buys get a protective bracket** — a stop-loss and take-profit
  attached automatically from your Settings.

If an order is rejected you'll see exactly why (e.g. "position would be 14% of
equity (max 10%)").

---

## 5. Place a trade

- **Quick entry:** the **Buy** button on a Recommendations row places a
  paper market buy.
- **Exact size:** use the **Ticker** trade panel and type a quantity.
- **Exit:** **Sell → Confirm** on a Dashboard position row closes the whole
  position; or use the **Sell** button on the Ticker panel for a partial exit.

> **Broker's note — a sizing gotcha to know:** the one-click **Buy** auto-sizes
> to your **max-position cap**, *not* the smaller volatility-targeted "suggested
> qty" shown in the expanded row. If you want the risk-targeted size, type that
> quantity into the Ticker panel. (The auto-trader, §6, also handles SELL exits
> on its own.)

---

## 6. (Optional) Let it run on autopilot — paper only

In **Settings → Automation**, toggle **Auto-trade**. During market hours the
scheduler will, each cycle: **sell** any holding that flipped to SELL, and **buy**
the top-ranked BUYs you don't already hold (risk caps decide how many actually
fill). It uses auto-sizing and the same risk gate.

> **Hard safety guarantee:** auto-trade is **structurally paper-only**. It cannot
> supply the per-order live confirmation the live gate requires, so it can never
> place a real-money order — by construction, not by configuration.

Autopilot is deliberately simple: it does not rebalance existing sizes, scale in,
or trail stops beyond the initial bracket. Treat it as a hands-off paper
experiment, and check the **auto-actions** it reports.

---

## 7. Validate before you believe (Backtest tab)

**This is the step that separates a hunch from an edge — do not skip it.**

1. Enter symbols, a date range, starting cash, and stop/target. Toggle the regime
   filter and vol-targeted sizing to match how you'd trade live.
2. **Run backtest.** Read: total return **vs buy-and-hold**, Sharpe/Sortino, max
   drawdown, win rate, profit factor, exposure, turnover, per-signal **P&L
   attribution**, and the **equity curve vs benchmark**. Beating an equal-weight
   buy-and-hold *after* costs is the bar.
3. **Validate** the result is real, not curve-fit:
   - **Walk-forward** — picks the buy threshold on each training fold and trades
     it on the *next unseen* fold. The out-of-sample numbers are the honest ones.
   - **Parameter sweep** — a heatmap of Sharpe across thresholds × signal tilts.
     A broad green plateau = robust; a lone bright cell = overfit, don't trust it.

> **Backtest honesty (built in).** Backtests run **technical + volatility +
> momentum + regime only** — sentiment and fundamentals are excluded because
> point-in-time historical news/fundamentals aren't available and using today's
> values would be look-ahead bias. Fills are at the next bar's open with slippage
> + commission; stops/targets checked intrabar. Survivorship bias and IEX-only
> data coverage still apply — interpret conservatively.

---

## 8. Relative-strength view (Research tab)

The **Research** tab gives a regime detail panel and a **relative-strength
leaderboard** — the universe sorted by the cross-sectional momentum signal, with
raw momentum and ATR%. Use it to see *what's leading* independent of the
composite BUY/SELL call.

---

## What syncs to your Alpaca account

Everything that matters is **Alpaca-native** — the app uses your Alpaca paper
account as the source of truth, so logging in to the Alpaca site shows the same
state:

| In the app | On the Alpaca site |
|------------|--------------------|
| Buy / Sell / close position | Orders & fills in your paper order history |
| Cancel (Open Orders panel) | The order is cancelled on Alpaca |
| Stop-loss / take-profit bracket | The attached OCO child orders |
| Open positions, equity, cash, buying power | Read live from your Alpaca account |
| Watchlist | Mirrored to a **"StockSim"** watchlist (auto + manual sync) |

Recommendations, the regime read, and backtests are computed locally from Alpaca
market data — they're analysis layers, not account state, so they don't appear on
the Alpaca site (by nature).

---

## A sensible daily routine

1. **Open the Dashboard** — check equity, open P&L, and the **regime**.
2. **Recommendations → Refresh now** — scan the ranked list; expand the top few
   and *read the reasons and agreement*, not just the score.
3. **Cross-check on the Ticker page** — chart, news, and the risk-checked panel.
4. **Act deliberately** — enter via the Ticker panel at a size you've decided on;
   the bracket stop/target goes on automatically.
5. **Manage exits** — review open positions and working orders on the Dashboard;
   **Sell → Confirm** to close a position when a thesis breaks or a name flips to
   SELL, and **Cancel** any stale working order.
6. **Before adopting any new rule or weight, prove it in the Backtest tab** with
   walk-forward, then on paper for several weeks.

Because signals are computed on **daily bars**, the most informative time to run
this is near or just after the close. Intraday refreshes mostly update prices,
not the underlying daily signals.

---

## Paper-only by design

**This app is a paper-trading simulator on the Alpaca API** — by design it places
**paper orders only**. The header stays **● PAPER**, the auto-trader is
structurally paper-only, and the live-trading kill switch (`LIVE_TRADING`,
non-paper endpoint, per-order confirmation) remains in the code but the UI does
not surface a live-order path. There is no real money at risk. If you ever decide
to pursue real-money trading, that is a separate, deliberate engineering step —
and only worth considering after a strategy has shown an out-of-sample edge **and**
weeks of profitable paper trading.

---

## Known limitations (read before you rely on it)

| Area | Limitation |
|------|------------|
| **One-click sizing** | Recommendations "Buy" sizes to the max-position cap, not the displayed vol-targeted suggested qty — use the Ticker qty field to match the suggestion. |
| **Realized P&L / trade journal** | Not surfaced in the UI; orders are persisted in the DB and recommendation history is available via the API. |
| **Horizon** | Daily-bar swing/position trading — not intraday. |
| **Backtest scope** | Sentiment & fundamentals excluded (look-ahead honesty); survivorship & IEX coverage caveats apply. |

Flagged here so you trade (on paper) with eyes open.
