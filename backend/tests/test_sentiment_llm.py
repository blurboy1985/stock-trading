from types import SimpleNamespace

from app.strategies import sentiment, sentiment_llm


def test_llm_sentiment_uses_hermes_chatgpt_cli(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout='{"scores":[{"index":0,"polarity":0.75}]}',
            stderr="",
        )

    monkeypatch.setattr(sentiment_llm.subprocess, "run", fake_run)
    monkeypatch.setattr(sentiment_llm.settings, "hermes_cli", "hermes")
    monkeypatch.setattr(sentiment_llm.settings, "chatgpt_sentiment_model", "gpt-5.5")
    sentiment_llm._CACHE.clear()

    scores = sentiment_llm.batch_polarity(
        [{"headline": "Strong earnings beat", "summary": "Guidance was raised."}]
    )

    assert scores == {"Strong earnings beat. Guidance was raised.": 0.75}
    cmd, kwargs = calls[0]
    assert cmd[0] == "hermes"
    assert "claude" not in cmd
    assert "--model" in cmd
    assert cmd[cmd.index("--model") + 1] == "gpt-5.5"
    assert "-z" in cmd
    assert "--ignore-rules" in cmd
    assert kwargs["timeout"] == sentiment_llm._TIMEOUT_S


def test_llm_sentiment_falls_back_on_cli_failure(monkeypatch):
    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="not logged in")

    monkeypatch.setattr(sentiment_llm.subprocess, "run", fake_run)
    sentiment_llm._CACHE.clear()

    assert sentiment_llm.batch_polarity(
        [{"headline": "Some headline", "summary": "Some summary"}]
    ) == {}


def test_llm_sentiment_can_skip_misses_and_use_lexicon_fallback(monkeypatch):
    def fail_if_called(*args, **kwargs):  # pragma: no cover - assertion helper
        raise AssertionError("should not launch Hermes for cache misses")

    monkeypatch.setattr(sentiment_llm.subprocess, "run", fail_if_called)
    sentiment_llm._CACHE.clear()

    item = {"headline": "Company beats earnings and raises guidance", "summary": ""}
    assert sentiment_llm.batch_polarity([item], query_missing=False) == {}

    res = sentiment.score_headlines([item], backend="llm", llm_query_missing=False)
    assert res.metrics["backend"] == "lexicon"
    assert "finance lexicon" in res.reasons[0]
    assert res.score > 0
