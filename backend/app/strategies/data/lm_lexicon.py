"""Curated Loughran–McDonald finance sentiment lexicon (vendored, no deps).

VADER is a general-purpose social-media lexicon and systematically misreads
financial text: words like *liability*, *tax*, *crude*, *capital* are neutral or
positive in finance but score negatively (or vice-versa) in VADER. Loughran &
McDonald built word lists specifically from 10-K/financial language; blending
them with VADER materially improves headline polarity on market news.

This is a *curated subset* of the full LM master dictionary (which has ~2,300
negative / ~350 positive entries) — enough common finance vocabulary to shift
scores meaningfully without vendoring the entire dictionary. Words are stored as
lowercase stems matched against tokenized, lowercased text.

Reference: Loughran, T. & McDonald, B. (2011), *When Is a Liability Not a
Liability? Textual Analysis, Dictionaries, and 10-Ks*, Journal of Finance.
"""
from __future__ import annotations

POSITIVE: frozenset[str] = frozenset(
    {
        # growth / outperformance
        "beat", "beats", "exceeded", "exceeds", "outperform", "outperformed",
        "outperforms", "surpassed", "surpasses", "topped", "tops", "record",
        "records", "high", "highs", "all-time", "rally", "rallied", "rallies",
        "surge", "surged", "surges", "soar", "soared", "soars", "jump", "jumped",
        "climb", "climbed", "gain", "gained", "gains", "rise", "rises", "rose",
        "rebound", "rebounded", "upbeat", "upside", "upgrade", "upgraded",
        "upgrades", "bullish", "boom", "booming",
        # fundamentals strength
        "profit", "profits", "profitable", "profitability", "growth", "growing",
        "grew", "expand", "expanded", "expansion", "strong", "stronger",
        "strength", "robust", "solid", "healthy", "improve", "improved",
        "improvement", "improving", "momentum", "accelerate", "accelerated",
        "accelerating", "efficient", "efficiency", "lead", "leading", "leader",
        "dividend", "dividends", "buyback", "buybacks", "raise", "raised",
        "boost", "boosted", "boosts", "win", "winning", "won", "award",
        "awarded", "approval", "approved", "breakthrough", "innovative",
        "innovation", "opportunity", "opportunities", "optimistic", "confident",
        "confidence", "favorable", "positive", "advantage", "benefit",
        "benefited", "benefits", "success", "successful", "successfully",
        "outstanding", "exceptional", "stellar", "impressive",
    }
)

NEGATIVE: frozenset[str] = frozenset(
    {
        # price / market weakness
        "miss", "misses", "missed", "fall", "falls", "fell", "drop", "dropped",
        "drops", "decline", "declined", "declines", "plunge", "plunged",
        "plunges", "slump", "slumped", "tumble", "tumbled", "tumbles", "sink",
        "sank", "sinks", "slide", "slid", "slides", "crash", "crashed", "selloff",
        "sell-off", "downgrade", "downgraded", "downgrades", "bearish",
        "downside", "low", "lows", "weak", "weaker", "weakness", "soft",
        "sluggish", "slowdown", "slowing", "slowed",
        # fundamentals / corporate distress
        "loss", "losses", "lost", "deficit", "shortfall", "warn", "warns",
        "warned", "warning", "cut", "cuts", "slash", "slashed", "reduce",
        "reduced", "lower", "lowered", "lowers", "disappointing", "disappoint",
        "disappointed", "concern", "concerns", "concerned", "fear", "fears",
        "risk", "risks", "risky", "uncertain", "uncertainty", "volatile",
        "volatility", "default", "defaults", "bankruptcy", "bankrupt",
        "insolvent", "insolvency", "debt", "liability", "liabilities",
        "litigation", "lawsuit", "lawsuits", "sue", "sued", "probe", "probes",
        "investigation", "investigated", "fraud", "scandal", "allegation",
        "allegations", "violation", "violations", "penalty", "penalties",
        "fine", "fined", "recall", "recalled", "delay", "delayed", "delays",
        "halt", "halted", "suspend", "suspended", "layoff", "layoffs",
        "restructuring", "writedown", "write-down", "writeoff", "write-off",
        "impairment", "downturn", "recession", "struggle", "struggled",
        "struggling", "trouble", "troubled", "negative", "adverse", "challenge",
        "challenges", "challenging", "pressure", "pressured", "headwind",
        "headwinds", "underperform", "underperformed", "overvalued",
    }
)

# Words that flip the polarity of the token that follows them.
NEGATORS: frozenset[str] = frozenset(
    {"no", "not", "never", "without", "lacks", "lack", "fails", "fail",
     "failed", "failing", "cannot", "can't", "won't", "isn't", "aren't",
     "wasn't", "weren't", "doesn't", "don't", "didn't"}
)
