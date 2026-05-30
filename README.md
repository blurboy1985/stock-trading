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
| Momentum      | Cross-sectional 12-1 relative strength, ranked vs the universe |
| Sentiment     | VADER + a finance lexicon (Loughran–McDonald) over recent news, recency-weighted and de-duped; optional Claude LLM backend |
| Fundamentals  | yfinance multi-factor value/growth/quality/health, scored relative to the live sector median |

`scoring.combine()` weights them (configurable in Settings) into a final
composite that maps to **BUY / SELL / HOLD**. The backtester reuses the *exact
same* signal functions, so backtested decisions match live decisions.

**Safety** — every order passes `services/risk.py` (position-size cap, total
exposure cap, buying-power check, stop-loss/take-profit bracket). The app runs
**paper-only**: real-money orders would require all three of `LIVE_TRADING=true`
in `.env`, a non-paper Alpaca endpoint, **and** an explicit per-order
confirmation flag — and the UI never sends that flag, so every UI order is a
paper order.

Auto-trading (the scheduler acting on recommendations) is likewise **structurally
limited to paper** — it cannot supply the per-order live confirmation, so it can
never place a real-money order.

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

📖 **For the full step-by-step daily workflow, read [GUIDE.md](GUIDE.md)** —
setup, configuring, reading recommendations, placing risk-checked trades,
backtesting/validation, a sensible daily routine, and the known limitations.

The tabs at a glance:

- **Dashboard** — account equity, today's P&L, market regime, open positions
  (with one-click **Sell → Confirm** to close), open/working orders (with
  **Cancel**), and top buy signals.
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
- **Settings** — broker/safety status, auto-trade toggle, signal weights,
  sentiment/fundamentals tuning, quant controls, risk limits, and watchlist.

### Backtesting honesty
Backtests use **technical + volatility only**. Point-in-time historical news and
fundamentals aren't available, so including today's values would be look-ahead
bias. Fills execute at the next bar's open with configurable slippage and
commission; there is no look-ahead and stops/targets are checked intrabar.
Survivorship bias and IEX-only data coverage still apply — interpret results
conservatively.

---

## Paper-only by design
This app is a **paper-trading simulator** on the Alpaca API — it places paper
orders only. The header stays **● PAPER**, auto-trading is structurally
paper-only, and the live-trading kill switch (`LIVE_TRADING` + non-paper endpoint
+ per-order confirmation) remains in the code but the UI does not surface a
real-money order path. No real capital is at risk. Pursuing live trading would be
a separate, deliberate step — and only after a strategy has shown an
out-of-sample edge **and** weeks of profitable paper trading. See
[GUIDE.md](GUIDE.md).

---

## Tests
```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q
```
Covers indicators, signal directionality, composite scoring, and the backtest
engine (including stop-loss behavior and flat-market no-edge checks).
