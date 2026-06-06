# Contributing to StockSim

Thanks for your interest in improving StockSim! This is a learning/simulation tool for
retail traders, and contributions that make it safer, clearer, or better-tested are very
welcome.

> **Safety first.** StockSim is paper-only by design. Any change that touches order
> execution, the live-trading gate, or risk checks gets extra scrutiny. Never weaken a
> safety gate without a clear, discussed reason.

## Ways to contribute

- **Bug reports** — open an issue with steps to reproduce, expected vs. actual behavior,
  and your OS / Python / Node versions.
- **Features & signals** — propose new indicators, signal families, or backtest metrics in
  an issue first so we can agree on scope before you build.
- **Docs** — fixes to the README, GUIDE, or inline docstrings are always appreciated.
- **Tests** — additional coverage for the signal engine, scoring, or backtester is
  high-value.

## Development setup

**Backend (FastAPI + Python):**
```bash
cd backend
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt   # Windows: .venv\Scripts\python.exe
cp .env.example .env          # leave keys blank to run unconfigured
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

**Frontend (React + Vite + TS):**
```bash
cd frontend
npm install
npm run dev
```

## Before you open a pull request

1. **Run the tests** — `cd backend && python -m pytest -q`. All tests must pass.
2. **Keep diffs focused** — one logical change per PR.
3. **No secrets** — never commit a real `.env`, API key, or account data. Only
   `.env.example` (with blank placeholders) belongs in the repo.
4. **Update docs** — if behavior changes, update the README / GUIDE.
5. **Describe the change** — what, why, and how you tested it.

## Reporting a security issue

If you find a vulnerability (e.g. a way to bypass the paper-only gate or leak credentials),
please **do not** open a public issue. Email the maintainer or open a private security
advisory on GitHub instead.

## Code of conduct

Be respectful and constructive. We're here to learn and build something useful together.
