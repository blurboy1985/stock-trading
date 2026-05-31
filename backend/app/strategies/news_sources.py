"""Multi-source news aggregation with event-level de-duplication.

Alpaca's news feed is Benzinga-only. Pulling additional providers (Yahoo
Finance, Finnhub, Marketaux, NewsAPI) broadens publisher coverage — but naively
concatenating them *biases* the sentiment signal: the same story reported by ten
outlets becomes ten weighted "votes" and manufactures fake consensus (low
dispersion ⇒ inflated confidence). So before scoring we **cluster articles by
event** (title similarity within a time window) and keep one representative per
cluster, so the signal counts *distinct events, not articles*.

All sources are best-effort: a missing key, dependency, or network error yields
an empty list and never breaks a scoring cycle. External providers are opt-in
via the ``news_sources`` setting and (by default) scoped to the watchlist so a
broad universe scan stays fast.
"""
from __future__ import annotations

import datetime as dt
import re
import time
from typing import Any

from .. import alpaca_client as ac
from ..config import settings

# Sources usable with no extra key (yfinance ships as a fundamentals dep).
ALWAYS_AVAILABLE = ("alpaca", "yfinance")
# Sources gated on an API key in the environment.
KEYED_SOURCES = ("finnhub", "marketaux", "newsapi")
ALL_SOURCES = (*ALWAYS_AVAILABLE, *KEYED_SOURCES)

# Event-clustering knobs.
_DUP_JACCARD = 0.5      # title token-set overlap above which two stories = one event
_WINDOW_HOURS = 48.0    # ...and only if published within this window of each other

# Short TTL cache for the rate-limited HTTP providers (per source+symbol).
_CACHE: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}
_CACHE_TTL = 600.0  # 10 min

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9'\-]+")
# Tiny stopword set so common filler doesn't manufacture title similarity.
_STOP = frozenset(
    "the a an and or of to in on for with at by from is are be as its it this "
    "that into after over amid will would could may says said new".split()
)


# ── key / availability ────────────────────────────────────────────────────


def _key(source: str) -> str:
    return {
        "finnhub": settings.finnhub_api_key,
        "marketaux": settings.marketaux_api_key,
        "newsapi": settings.newsapi_api_key,
    }.get(source, "")


def available_sources() -> list[str]:
    """Sources that are actually usable right now (deps + keys present)."""
    return [*ALWAYS_AVAILABLE, *(s for s in KEYED_SOURCES if _key(s))]


# ── small helpers ──────────────────────────────────────────────────────────


def _parse_dt(value: Any) -> dt.datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return dt.datetime.fromtimestamp(value, tz=dt.timezone.utc)
        d = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def _title_tokens(text: str) -> frozenset[str]:
    return frozenset(t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def _http_get_json(url: str, params: dict[str, Any], timeout: float = 6.0) -> Any:
    """GET JSON, returning ``None`` on any failure (best-effort)."""
    try:
        import httpx

        r = httpx.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:  # noqa: BLE001 — every external source is best-effort
        return None


# ── per-source fetchers (all normalize to our common item shape) ────────────


def _yfinance_one(symbol: str, limit: int) -> list[dict[str, Any]]:
    return ac._yf_news([symbol], limit)


def _finnhub_one(symbol: str, limit: int) -> list[dict[str, Any]]:
    today = dt.date.today()
    data = _http_get_json(
        "https://finnhub.io/api/v1/company-news",
        {
            "symbol": symbol,
            "from": (today - dt.timedelta(days=14)).isoformat(),
            "to": today.isoformat(),
            "token": _key("finnhub"),
        },
    )
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for n in data[:limit]:
        headline = (n.get("headline") or "").strip()
        if not headline:
            continue
        created = _parse_dt(n.get("datetime"))
        out.append(
            {
                "headline": headline,
                "summary": n.get("summary") or "",
                "symbols": [symbol],
                "source": n.get("source") or "Finnhub",
                "url": n.get("url") or "",
                "created_at": created.isoformat() if created else None,
            }
        )
    return out


def _marketaux_one(symbol: str, limit: int) -> list[dict[str, Any]]:
    data = _http_get_json(
        "https://api.marketaux.com/v1/news/all",
        {
            "symbols": symbol,
            "filter_entities": "true",
            "language": "en",
            "limit": min(limit, 50),
            "api_token": _key("marketaux"),
        },
    )
    rows = (data or {}).get("data") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for n in rows[:limit]:
        headline = (n.get("title") or "").strip()
        if not headline:
            continue
        created = _parse_dt(n.get("published_at"))
        out.append(
            {
                "headline": headline,
                "summary": n.get("description") or n.get("snippet") or "",
                "symbols": [symbol],
                "source": n.get("source") or "Marketaux",
                "url": n.get("url") or "",
                "created_at": created.isoformat() if created else None,
            }
        )
    return out


def _newsapi_one(symbol: str, limit: int) -> list[dict[str, Any]]:
    # NewsAPI is keyword-based (no ticker filter); quote the symbol to reduce
    # noise. Crude vs. the finance-native feeds, hence opt-in.
    data = _http_get_json(
        "https://newsapi.org/v2/everything",
        {
            "q": f'"{symbol}"',
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": min(limit, 50),
            "apiKey": _key("newsapi"),
        },
    )
    rows = (data or {}).get("articles") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for n in rows[:limit]:
        headline = (n.get("title") or "").strip()
        if not headline:
            continue
        created = _parse_dt(n.get("publishedAt"))
        out.append(
            {
                "headline": headline,
                "summary": n.get("description") or "",
                "symbols": [symbol],
                "source": (n.get("source") or {}).get("name") or "NewsAPI",
                "url": n.get("url") or "",
                "created_at": created.isoformat() if created else None,
            }
        )
    return out


_FETCHERS = {
    "yfinance": _yfinance_one,
    "finnhub": _finnhub_one,
    "marketaux": _marketaux_one,
    "newsapi": _newsapi_one,
}


def fetch_one(source: str, symbol: str, limit: int) -> list[dict[str, Any]]:
    """Fetch one source for one symbol, cached and best-effort (never raises)."""
    fn = _FETCHERS.get(source)
    if fn is None:
        return []
    now = time.time()
    ck = (source, symbol)
    cached = _CACHE.get(ck)
    if cached and now - cached[0] < _CACHE_TTL:
        return cached[1]
    try:
        items = fn(symbol, limit)
    except Exception:  # noqa: BLE001
        items = []
    _CACHE[ck] = (now, items)
    return items


# ── event-level de-duplication ──────────────────────────────────────────────


def event_dedup(
    items: list[dict[str, Any]],
    *,
    jaccard: float = _DUP_JACCARD,
    window_hours: float = _WINDOW_HOURS,
) -> list[dict[str, Any]]:
    """Collapse same-event articles to one representative, newest-first.

    Greedy clustering on title-token Jaccard within a time window. The earliest
    article in a cluster is kept (closest to the event); it's enriched with the
    union of related ``symbols``, the contributing ``sources``, and a
    ``cluster_size`` so downstream code counts events rather than articles.
    """
    enriched = [
        (_parse_dt(it.get("created_at")), _title_tokens(it.get("headline", "")), it)
        for it in items
    ]
    # Earliest first so the representative is the original report; undated last.
    far_future = dt.datetime.max.replace(tzinfo=dt.timezone.utc)
    enriched.sort(key=lambda x: x[0] or far_future)

    clusters: list[dict[str, Any]] = []
    for ts, toks, it in enriched:
        placed = False
        if toks:
            for c in clusters:
                if _jaccard(toks, c["toks"]) < jaccard:
                    continue
                if ts is not None and c["ts"] is not None:
                    if abs((ts - c["ts"]).total_seconds()) > window_hours * 3600:
                        continue
                c["size"] += 1
                c["sources"].add(it.get("source") or "")
                c["symbols"].update(it.get("symbols") or [])
                placed = True
                break
        if not placed:
            clusters.append(
                {
                    "rep": it,
                    "toks": toks,
                    "ts": ts,
                    "size": 1,
                    "sources": {it.get("source") or ""},
                    "symbols": set(it.get("symbols") or []),
                }
            )

    out: list[dict[str, Any]] = []
    for c in clusters:
        rep = dict(c["rep"])
        rep["symbols"] = sorted(s for s in c["symbols"] if s)
        rep["sources"] = sorted(s for s in c["sources"] if s)
        rep["cluster_size"] = c["size"]
        out.append(rep)
    out.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return out


# ── orchestration for the recommender ───────────────────────────────────────


def build_symbol_news(
    universe: list[str],
    watchlist_set: set[str],
    base_news: dict[str, list[dict[str, Any]]],
    cfg: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Merge configured sources into per-symbol, event-deduped news.

    ``base_news`` is the already-fetched Alpaca/Benzinga news for the whole
    universe (one batched call). When extra sources are enabled we fetch them
    per-symbol for the scoped subset (watchlist by default), combine, and
    collapse to distinct events. Symbols outside the scope keep the Alpaca feed
    untouched — identical to the previous behavior.
    """
    sources = list(cfg.get("news_sources") or ["alpaca"])
    usable = set(available_sources())
    extra = [s for s in sources if s != "alpaca" and s in usable]

    out = {s: list(base_news.get(s, [])) for s in universe}
    if not extra:
        return out  # nothing to add → current Alpaca-only behavior

    include_alpaca = "alpaca" in sources
    scope = cfg.get("news_scope", "watchlist")
    universe_set = set(universe)
    targets = sorted(
        (watchlist_set & universe_set) if scope == "watchlist" else universe_set
    )
    per = int(cfg.get("news_per_source_limit", 15))

    for sym in targets:
        items = list(out.get(sym, [])) if include_alpaca else []
        for src in extra:
            items.extend(fetch_one(src, sym, per))
        out[sym] = event_dedup(items)
    return out
