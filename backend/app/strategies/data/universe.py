"""A curated, stable universe of liquid US large/mid-caps.

The default scan uses the day's *most-active* names, which is recency-biased:
it's dominated by crowded, news-driven, mean-reverting chop and the day's
blowups/squeezes — exactly the names where momentum/relative-strength signals
don't persist. A swing strategy wants relative-strength *leaders* drawn from a
*persistent* liquid set, so the cross-sectional momentum rank (already computed
each cycle) ranks the same pond over time rather than a shifting cast.

This list is intentionally broad and diversified across sectors, ordered roughly
by liquidity/market cap so that capping it at ``universe_size`` keeps the most
tradable names. It is not an index; it's a sane, liquid default the user can
extend via the watchlist (which is always unioned in).
"""
from __future__ import annotations

# ~120 liquid names across all 11 GICS sectors, cap-ordered-ish.
CORE_LIQUID_UNIVERSE: list[str] = [
    # Mega-cap tech / comms
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA", "ORCL",
    "ADBE", "CRM", "AMD", "CSCO", "ACN", "INTC", "QCOM", "TXN", "IBM", "NFLX",
    "INTU", "NOW", "AMAT", "MU", "ADI", "LRCX", "KLAC", "SNPS", "CDNS", "PANW",
    # Communication / media
    "DIS", "CMCSA", "T", "VZ", "TMUS",
    # Consumer discretionary
    "HD", "MCD", "NKE", "LOW", "SBUX", "BKNG", "TJX", "ABNB", "MAR", "GM", "F",
    # Consumer staples
    "WMT", "PG", "KO", "PEP", "COST", "MDLZ", "CL", "MO", "PM", "TGT",
    # Financials
    # Exclude BRK.B/BRK-B: Yahoo and IBKR use different class-share symbols,
    # which makes automated research/order routing unreliable in this app.
    "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "AXP", "SCHW", "BLK",
    "C", "SPGI", "CB", "PYPL",
    # Health care
    "UNH", "JNJ", "LLY", "ABBV", "MRK", "PFE", "TMO", "ABT", "DHR", "BMY",
    "AMGN", "GILD", "CVS", "MDT", "ISRG", "VRTX", "REGN",
    # Industrials
    "CAT", "BA", "HON", "UNP", "GE", "RTX", "DE", "LMT", "UPS", "ETN", "EMR",
    # Energy
    "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX",
    # Materials
    "LIN", "SHW", "FCX", "NEM", "APD",
    # Utilities
    "NEE", "DUK", "SO", "D",
    # Real estate
    "AMT", "PLD", "EQIX", "SPG",
    # Liquid sector / broad ETFs (for breadth + always-tradable RS anchors)
    "SPY", "QQQ", "IWM", "DIA",
]
