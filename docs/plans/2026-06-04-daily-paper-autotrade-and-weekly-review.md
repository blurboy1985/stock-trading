# Daily Paper Auto-Trade and One-Week Review Plan

> **For Hermes:** This is an operational plan for safely running StockSim on IBKR paper trading during US trading days, measuring whether it is useful, and improving it if it loses money. Do not convert this into live trading without a separate explicit approval.

**Goal:** Run StockSim's paper-only auto-trader on US trading days for one week, record objective performance, fix operational issues, and recommend improvements if results are negative.

**Architecture:** StockSim already has a FastAPI backend, React frontend, IBKR adapter, background scheduler, runtime `auto_trade` setting, `/api/portfolio/history`, `/api/portfolio/activities`, `/api/recommendations`, and paper/live safety gates. This plan uses the existing app and adds an operating cadence plus monitoring checkpoints rather than changing the trading engine first.

**Tech Stack:** Python/FastAPI backend in `backend/`, SQLite DB `backend/stock_trader.db`, IBKR Gateway paper on `127.0.0.1:4002`, frontend on Vite `:5173`, Hermes cron monitoring.

---

## Current observed state on 2026-06-04 18:58 SGT

- Repo inspected: `/home/danielquek/stock-trading`, branch `IBKR`.
- `.env` safety/broker state:
  - `BROKER=ibkr`
  - `IBKR_HOST=127.0.0.1`
  - `IBKR_PORT=4002`
  - `IBKR_CLIENT_ID=112`
  - `IBKR_TRADING_MODE=paper`
  - `TRADING_ENABLED=true`
  - `LIVE_TRADING=false`
- Runtime settings in `backend/stock_trader.db` show `auto_trade=true`, `buy_threshold=0.25`, `sell_threshold=-0.25`, `max_position_pct=0.1`, `max_total_exposure_pct=0.8`, `trailing_stop_enabled=false`, and `trailing_stop_dry_run=true`.
- No listener was found on backend `:8000`, frontend `:5173`, IBKR Gateway paper `:4002`, or TWS paper `:7497` at inspection time.
- Therefore auto-trade is configured in the database, but daily auto-trading cannot actually run until IBKR paper Gateway/TWS and the backend are running.

---

## Safety boundaries

1. Keep `IBKR_TRADING_MODE=paper` and `LIVE_TRADING=false` for the whole experiment.
2. Do not place live-money orders; this experiment is paper-only.
3. Let StockSim's own risk gate submit any paper orders; do not place ad-hoc orders from monitoring scripts.
4. If the app reports broker errors, stale orders, missing positions, or unexpected losses, pause `auto_trade` first, then diagnose.
5. Treat IBKR as the source of truth for equity, positions, orders, and fills.

---

## Trading-day operating plan

### Task 1: Pre-market readiness check, every US trading day

**Objective:** Confirm the app can trade paper safely before the scheduler is allowed to act.

**Files / endpoints:**
- Inspect: `backend/.env`
- Endpoint: `GET http://127.0.0.1:8000/health`
- Endpoint: `GET http://127.0.0.1:8000/api/settings`
- Endpoint: `GET http://127.0.0.1:8000/api/portfolio`
- Endpoint: `GET http://127.0.0.1:8000/api/portfolio/orders?status=all`

**Steps:**
1. Verify IBKR Gateway/TWS paper is logged in and API socket is listening on `4002` or `7497`.
2. Start backend if it is not running:
   ```bash
   cd /home/danielquek/stock-trading/backend
   .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```
3. Start frontend only if UI access is needed:
   ```bash
   cd /home/danielquek/stock-trading/frontend
   npm run dev -- --host 127.0.0.1
   ```
4. Verify `/health` says `is_paper=true`, `trading_enabled=true`, and `live_trading_enabled=false`.
5. Verify `/api/settings` has `settings.auto_trade=true` for auto-trade days. If it is false, enable it intentionally through the UI or:
   ```bash
   curl -s -X PUT http://127.0.0.1:8000/api/settings \
     -H 'Content-Type: application/json' \
     -d '{"auto_trade":true}'
   ```
6. Verify portfolio and order endpoints return cleanly.

**Pass criteria:** backend healthy, broker connected, paper mode true, live trading false, auto-trade true, no unexplained stale/pending orders.

**Fail-safe:** If any check fails, keep/turn `auto_trade=false` and fix the issue before the next market session.

---

### Task 2: Let the app trade only during regular US market hours

**Objective:** Use the existing StockSim scheduler instead of external order scripts.

**How it works:**
- The backend scheduler refreshes recommendations every 15 minutes during market hours.
- When `auto_trade=true`, it sells holdings that flip to SELL and buys top-ranked BUYs not already held, subject to risk caps.
- Auto-trade is structurally paper-only and cannot supply live confirmation.

**Guardrails for week 1:**
- Keep default watchlist unless there is a specific reason to change it.
- Keep max position size at or below 10% and max total exposure at or below 80%.
- Keep stop loss / take profit defaults unless backtests justify a change.
- Keep trailing-stop dry-run on for the first week unless behavior is reviewed.

---

### Task 3: End-of-day capture, every US trading day

**Objective:** Record daily evidence for profit/usefulness measurement.

**Capture:**
- Account equity / buying power / cash from `/api/portfolio`.
- Open positions from `/api/portfolio`.
- Open + pending orders from `/api/portfolio/orders?status=all`.
- Filled trades from `/api/portfolio/activities?activity_types=FILL&page_size=100`.
- Portfolio history from `/api/portfolio/history?period=1M&timeframe=1D`.
- Latest recommendations from `/api/recommendations`.

**Daily note format:**
- Date:
- Market/session status:
- Starting equity:
- Ending equity:
- Realized P&L:
- Unrealized P&L:
- Net P&L:
- Return %:
- Number of trades:
- Largest winner / loser:
- Open risk at close:
- Issues encountered:
- Fixes applied:

---

## One-week usefulness review

### Task 4: Measure profit and compare against baseline

**Objective:** Decide whether StockSim helped after one week.

**Metrics:**
1. Net paper P&L and return percentage.
2. Realized vs unrealized P&L.
3. Win rate and average win/loss from fills.
4. Max drawdown during the week, if history data is available.
5. Turnover and number of trades.
6. Benchmark comparison: SPY over the same dates; optionally equal-weight watchlist buy-and-hold.
7. Quality of operations: number of broker/app failures and whether any required manual intervention.

**Decision rule:**
- Useful: positive return and beats SPY/equal-weight baseline after costs, with no major operational failures.
- Inconclusive: small profit/loss within normal noise, too few trades, or incomplete history.
- Not useful yet: negative return worse than baseline, repeated operational errors, excessive turnover, or risk controls causing poor fills.

---

### Task 5: If the app loses money, recommend improvements before another run

**Objective:** Improve the strategy systematically, not by guessing.

**Recommended improvement sequence:**
1. Pause `auto_trade`.
2. Run backtests and walk-forward validation over the current watchlist and settings.
3. Check if losses came from:
   - risk-off market regime ignored or too weak,
   - buy threshold too permissive,
   - sell threshold too slow,
   - max-position sizing too aggressive,
   - stops too tight or take-profit too wide,
   - sentiment/fundamentals noise,
   - specific symbols dominating losses,
   - after-hours pending order behavior.
4. Prefer conservative changes:
   - raise buy threshold,
   - lower max total exposure,
   - lower max position size,
   - enable stronger regime hard gate,
   - remove consistently poor/thin symbols from watchlist,
   - use vol-targeted sizing,
   - keep trailing stop dry-run until reviewed.
5. Re-run walk-forward/backtest after every proposed change.
6. Run another paper-only week before considering any further escalation.

---

## Operational checklist for Hermes monitoring

Daily monitor should report:
- Whether today is a US trading day.
- Whether IBKR paper socket is reachable.
- Whether backend is reachable.
- `/health` safety state.
- Whether `auto_trade` is enabled.
- Portfolio/equity snapshot if available.
- Orders/fills summary if available.
- Any failures and concrete fix attempts.

Weekly monitor should report:
- Week start/end equity.
- Net P&L and return %.
- SPY or watchlist benchmark comparison if obtainable.
- Trade count, win rate, average win/loss if fills are available.
- Operational issues fixed or still blocking.
- Recommendation: continue, pause, or modify strategy.

---

## Known blocker before first auto-trade session

At plan creation time, IBKR Gateway/TWS paper and backend were not running. Before auto-trading can happen, start/log in to IBKR paper Gateway/TWS and start the backend. If Gateway login requires credentials/2FA, enter them directly in IBKR; do not send credentials through chat.
