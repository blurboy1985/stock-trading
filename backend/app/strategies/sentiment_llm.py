"""Optional ChatGPT-backed headline sentiment scorer (off by default).

This is an alternative per-item polarity source for :mod:`.sentiment`. When the
``sentiment_backend`` runtime setting is ``"llm"``, :func:`batch_polarity`
scores a batch of headlines with ChatGPT/OpenAI and returns a polarity in ``[-1, 1]``
per headline.

Auth: it drives the local ``hermes`` CLI in one-shot mode, so it uses the same
Hermes-configured **ChatGPT/OpenAI subscription** as this agent session. There
is **no per-token API key and no ``OPENAI_API_KEY`` required** for this app.
Prerequisite: ``hermes`` is installed and authenticated for the default profile.

It is deliberately best-effort: **any** failure (CLI missing, not logged in,
timeout, malformed output) returns ``{}`` so the caller falls back to the
offline lexicon blend and a scoring cycle never breaks.
"""
from __future__ import annotations

import json
import re
import subprocess
from typing import Any

from ..config import settings

_TIMEOUT_S = 90.0  # hard cap so a wedged CLI can't stall a scoring cycle

# Headline-keyed memo of polarities. The recommender scores each symbol
# separately, but news items are shared across symbols and a headline's
# sentiment is stable — so we query ChatGPT once per *unseen* headline and reuse
# the result. Without this, a refresh fires one ~5s CLI call per symbol and a
# 12-symbol universe takes minutes (see ``prewarm`` below). Bounded so a
# long-running process can't grow it without limit.
_CACHE: dict[str, float] = {}
_CACHE_MAX = 2000

# Stable instruction prompt. The Agent SDK has no JSON-schema enforcement, so we
# instruct the model to emit only JSON and parse it defensively.
_SYSTEM = (
    "You are a financial-markets sentiment classifier. You receive a numbered "
    "list of news headlines (optionally with a summary) about publicly traded "
    "companies. For each item, judge how the news would affect the company's "
    "stock from an investor's perspective and assign a polarity from -1.0 "
    "(strongly bearish / bad for the stock) through 0.0 (neutral or irrelevant) "
    "to +1.0 (strongly bullish / good for the stock). Judge the financial "
    "implication, not the emotional tone of the wording.\n\n"
    "Respond with ONLY a JSON object of the form "
    '{"scores": [{"index": 0, "polarity": -0.4}, ...]} — one entry per input '
    "item, keyed by its index. No prose, no markdown fences."
)


def _item_text(item: dict[str, Any]) -> str:
    """Key used by :mod:`.sentiment` to look scores back up — keep in sync."""
    return f"{item.get('headline', '')}. {item.get('summary', '')}".strip()


def _build_prompt(items: list[dict[str, Any]]) -> tuple[str, dict[int, str]]:
    lines: list[str] = []
    index_to_text: dict[int, str] = {}
    for i, it in enumerate(items):
        text = _item_text(it)
        if not text:
            continue
        index_to_text[i] = text
        lines.append(f"[{i}] {text}")
    return "\n".join(lines), index_to_text


def _clamp(x: float) -> float:
    return max(-1.0, min(1.0, x))


def _parse_json(raw: str) -> dict[str, Any]:
    """Extract the JSON object from the model's reply (tolerates fences/prose)."""
    raw = raw.strip()
    if not raw:
        return {}
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        return json.loads(raw[start : end + 1])
    return {}


def _query_chatgpt(prompt: str, model: str | None) -> str:
    """Run a pure Hermes/ChatGPT one-shot completion and return stdout."""
    full_prompt = f"{_SYSTEM}\n\nHeadlines:\n{prompt}"
    cmd = [settings.hermes_cli, "-z", full_prompt, "-t", "safe", "--ignore-rules"]
    if model:
        cmd.extend(["--model", model])
    completed = subprocess.run(  # noqa: S603 — configured local CLI, no shell
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_S,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return completed.stdout


def batch_polarity(
    items: list[dict[str, Any]], model: str | None = None
) -> dict[str, float]:
    """Score a batch of news items with ChatGPT → ``{item_text: polarity}``.

    Headlines already in :data:`_CACHE` are served from it; only unseen
    headlines hit ChatGPT (a single call for the whole unseen batch). Returns
    ``{}`` on any failure so the caller falls back to the lexicon.
    """
    if not items:
        return {}

    # Partition into already-scored vs. needs-a-query (deduped by text).
    out: dict[str, float] = {}
    todo: dict[str, dict[str, Any]] = {}
    for it in items:
        text = _item_text(it)
        if not text:
            continue
        if text in _CACHE:
            out[text] = _CACHE[text]
        else:
            todo.setdefault(text, it)

    if todo:
        fresh = _query_items(list(todo.values()), model)
        for text, polarity in fresh.items():
            if len(_CACHE) < _CACHE_MAX:
                _CACHE[text] = polarity
            out[text] = polarity

    return out


def _query_items(
    items: list[dict[str, Any]], model: str | None
) -> dict[str, float]:
    """One ChatGPT call for ``items`` → ``{item_text: polarity}`` (``{}`` on error)."""
    prompt, index_to_text = _build_prompt(items)
    if not index_to_text:
        return {}

    chosen_model = model or settings.chatgpt_sentiment_model or None
    try:
        raw = _query_chatgpt(prompt, chosen_model)
        data = _parse_json(raw)
    except Exception:  # noqa: BLE001 — never break a scoring cycle on the LLM path
        return {}

    out: dict[str, float] = {}
    for row in data.get("scores", []):
        try:
            key = index_to_text.get(int(row["index"]))
            if key is not None:
                out[key] = _clamp(float(row["polarity"]))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def prewarm(items: list[dict[str, Any]], model: str | None = None) -> None:
    """Score every distinct headline in ``items`` in a single ChatGPT call so the
    recommender's per-symbol :func:`batch_polarity` calls become cache hits.

    Best-effort: any failure leaves the cache untouched and the per-symbol path
    falls back to the offline lexicon.
    """
    batch_polarity(items, model=model)
