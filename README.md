# 📈 StockSim — Multi-Signal Stock Trading Simulator

A US-stock **paper-trading simulator** that connects to Interactive Brokers
(IBKR) through TWS or IB Gateway, ranks the best stocks to buy/sell with a
transparent multi-signal engine, monitors open positions, and lets you validate
strategies with a rigorous backtester **before** risking real money.

Built with a broker abstraction and an IBKR adapter. Paper mode is the safe
default; live trading remains locked behind explicit configuration and per-order
confirmation.

> ⚠️ **Read this first.** This is a learning/simulation tool, not financial
> advice. No screener reliably beats the market, and most retail algorithmic
> strategies lose money after fees and slippage. Treat every recommendation as a
> hypothesis to be tested in the backtester and on paper. Do not commit real
> money until a strategy has demonstrated an edge over a meaningful out-of-sample
> period — and even then, only risk what you can afford to lose.

---

## Architecture

```
backend/    FastAPI + SQLite + IBKR broker adapter   (Python)
frontend/   React + Vite + TypeScript + Tailwind
```

**Signal engine** — every recommendation is a blend of four families, each
producing a normalized score in `[-1, +1]` plus a plain-English rationale:

| Family        | What it looks at                                            |
|---------------|-------------------------------------------------------------|
| Technical     | RSI, MACD, SMA/EMA crossovers, ADX-confirmed trend          |
| Volatility    | Donchian/Bollinger breakouts, ATR, volume spikes            |
| Momentum      | Cross-sectional 12-1 relative strength, ranked vs the universe |
| Sentiment     | VADER + a finance lexicon (Loughran–McDonald) over recent news, recency-weighted and de-duped; optional Claude LLM backend |
| Fundamentals  | yfinance multi-factor value/growth/quality/health, scored relative to the live sector median |

`scoring.combine()` weights them (configurable in Settings) into a final
composite that maps to **BUY / SELL / HOLD**. The backtester reuses the *exact
same* signal functions, so backtested decisions match live decisions.

**Safety** — every order passes `services/risk.py` (position-size cap, total
exposure cap, buying-power check, stop-loss/take-profit controls). Order
submission is disabled by default with `TRADING_ENABLED=false`. Real-money orders
require `IBKR_TRADING_MODE=live`, `LIVE_TRADING=true`, `TRADING_ENABLED=true`,
and an explicit per-order confirmation flag.

Auto-trading (the scheduler acting on recommendations) is likewise **structurally
limited to paper** — it cannot supply the per-order live confirmation, so it can
never place a real-money order.

---

## Setup

### 1. Start IBKR paper TWS or IB Gateway
Log in to an IBKR paper session and enable **API → Socket Clients**. No API key is
used for the normal IBKR socket API.

Default ports:
- IB Gateway paper: `127.0.0.1:4002`
- TWS paper: `127.0.0.1:7497`
- IB Gateway live: `127.0.0.1:4001`
- TWS live: `127.0.0.1:7496`

### 2. Backend
```powershell
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env       # keep IBKR paper defaults, or set IBKR_PORT=7497 for TWS paper
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```
Backend runs at <http://127.0.0.1:8000> (interactive docs at `/docs`).

### 3. Frontend
```powershell
cd frontend
npm install
npm run dev
```
Open <http://localhost:5173>. The Vite dev server proxies `/api` to the backend.

> The app imports and starts even when TWS/Gateway is not running. Broker-backed
> endpoints return clear "not connected" messages until the IBKR socket is ready.

---

## Using it

📖 **For the full step-by-step daily workflow, read [GUIDE.md](GUIDE.md)** —
setup, configuring, reading recommendations, placing risk-checked trades,
backtesting/validation, a sensible daily routine, and the known limitations.

The tabs at a glance:

- **Dashboard** — account equity, today's P&L, market regime, open positions
  (one-click **Sell → Confirm** closes a position and cancels its bracket first),
  open/working orders (with **Cancel**), and top buy signals.
- **Recommendations** — the watchlist ranked by a *risk-adjusted* score; expand
  any row for the per-signal breakdown, reasons, agreement, and suggested size.
  One-click paper buy.
- **Research** — market-regime detail and a relative-strength leaderboard.
- **Ticker** (`/ticker/AAPL`) — price chart, live quote, recent news, and a
  risk-checked paper trade panel (also where you exit a position).
- **Backtest** — symbols + date range + stop/target, run, and compare equity
  curve and metrics (Sharpe, max drawdown, win rate, profit factor) against an
  equal-weight buy-and-hold benchmark, with walk-forward + parameter-sweep
  validation.
- **History** — account P&L and equity curve over time plus a
  filled-order trade log.
- **Settings** — broker/safety status, auto-trade toggle, a trailing-stop
  ratchet (tightens held positions' bracket stops as price advances; dry-run by
  default), signal weights, sentiment/fundamentals tuning, quant controls, risk
  limits, and watchlist.

### Backtesting honesty
Backtests use **technical + volatility only**. Point-in-time historical news and
fundamentals aren't available, so including today's values would be look-ahead
bias. Fills execute at the next bar's open with configurable slippage and
commission; there is no look-ahead and stops/targets are checked intrabar
(gap-aware — a gap-through stop fills at the worse open, not the stop price).
Survivorship bias and IEX-only data coverage still apply — interpret results
conservatively.

---

## Paper-only by design
This app defaults to **IBKR paper trading**. The header should stay **● PAPER**,
`TRADING_ENABLED` defaults to `false`, and live trading requires a separate,
deliberate configuration change plus explicit per-order confirmation. No real
capital is at risk during the default setup. Pursuing live trading should only be
considered after a strategy has shown an out-of-sample edge **and** weeks of
profitable paper trading. See [GUIDE.md](GUIDE.md).

---

## Tests
```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q
```
Covers indicators, signal directionality, composite scoring, and the backtest
engine (including stop-loss behavior and flat-market no-edge checks).
