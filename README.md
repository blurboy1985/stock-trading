# 📈 StockSim — Multi-Signal Stock Trading Simulator

A US-stock **paper-trading simulator** that ingests market data from Alpaca,
ranks the best stocks to buy/sell with a transparent multi-signal engine,
monitors open positions, and lets you validate strategies with a rigorous
backtester **before** risking real money.

Built on Alpaca so the *same code* trades paper or live — going live is a config
change, not a rewrite.

> ⚠️ **Read this first.** This is a learning/simulation tool, not financial
> advice. No screener reliably beats the market, and most retail algorithmic
> strategies lose money after fees and slippage. Treat every recommendation as a
> hypothesis to be tested in the backtester and on paper. Do not commit real
> money until a strategy has demonstrated an edge over a meaningful out-of-sample
> period — and even then, only risk what you can afford to lose.

---

## Architecture

```
backend/    FastAPI + SQLite + Alpaca   (Python)
frontend/   React + Vite + TypeScript + Tailwind
```

**Signal engine** — every recommendation is a blend of four families, each
producing a normalized score in `[-1, +1]` plus a plain-English rationale:

| Family        | What it looks at                                            |
|---------------|-------------------------------------------------------------|
| Technical     | RSI, MACD, SMA/EMA crossovers, ADX-confirmed trend          |
| Volatility    | Donchian/Bollinger breakouts, ATR, volume spikes            |
| Sentiment     | VADER scoring of recent Alpaca news headlines               |
| Fundamentals  | yfinance P/E, revenue growth, margins (slow-moving tilt)    |

`scoring.combine()` weights them (configurable in Settings) into a final
composite that maps to **BUY / SELL / HOLD**. The backtester reuses the *exact
same* signal functions, so backtested decisions match live decisions.

**Safety** — every order passes `services/risk.py` (position-size cap, total
exposure cap, buying-power check, stop-loss/take-profit bracket). Live trading
is locked behind three independent gates:
1. `LIVE_TRADING=true` in `.env`
2. a non-paper Alpaca endpoint, and
3. explicit per-order confirmation from the UI.

Auto-trading (the scheduler acting on recommendations) is **structurally limited
to paper** — it cannot supply the per-order live confirmation, so it can never
place a real-money order.

---

## Setup

### 1. Get free Alpaca paper credentials
Sign up at <https://alpaca.markets>, open the **Paper Trading** dashboard, and
generate an API key + secret.

### 2. Backend
```powershell
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env       # then paste your APCA_API_KEY_ID / APCA_API_SECRET_KEY
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

> The app runs **without** credentials too — endpoints return a clear
> "not configured" message and the UI prompts you to add keys in Settings.

---

## Using it

- **Dashboard** — account equity, today's P&L, open positions, top buy signals.
- **Recommendations** — the watchlist ranked by composite score; expand any row
  to see the per-signal breakdown and reasons. One-click paper buy.
- **Ticker** (`/ticker/AAPL`) — candlestick chart, live quote, recent news, and a
  risk-checked paper trade panel.
- **Backtest** — pick symbols + date range + stop/target, run, and compare the
  strategy's equity curve and metrics (Sharpe, max drawdown, win rate, profit
  factor) against an equal-weight buy-and-hold benchmark.
- **Settings** — broker/safety status, auto-trade toggle, signal weights, risk
  limits, and watchlist management.

### Backtesting honesty
Backtests use **technical + volatility only**. Point-in-time historical news and
fundamentals aren't available, so including today's values would be look-ahead
bias. Fills execute at the next bar's open with configurable slippage and
commission; there is no look-ahead and stops/targets are checked intrabar.
Survivorship bias and IEX-only data coverage still apply — interpret results
conservatively.

---

## Going live (when you're ready, and at your own risk)
1. Confirm a strategy's edge across out-of-sample backtests **and** weeks of paper
   trading.
2. In `.env`: set `ALPACA_BASE_URL=https://api.alpaca.markets` and
   `LIVE_TRADING=true`, and use your **live** API keys.
3. Restart the backend. The header badge turns red (`● LIVE`) and each order now
   requires explicit confirmation.

---

## Tests
```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q
```
Covers indicators, signal directionality, composite scoring, and the backtest
engine (including stop-loss behavior and flat-market no-edge checks).
