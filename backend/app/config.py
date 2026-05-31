"""Application configuration loaded from environment / .env.

Everything in the app reads settings from the singleton ``settings`` object so
that API keys, risk parameters, and the live-trading kill switch live in exactly
one place.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ── Alpaca ────────────────────────────────────────────────────────
    apca_api_key_id: str = ""
    apca_api_secret_key: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"

    # ── External news providers (optional) ────────────────────────────
    # Used only when the matching source is enabled in the `news_sources`
    # setting. Each is best-effort: a missing key just disables that source.
    finnhub_api_key: str = ""
    marketaux_api_key: str = ""
    newsapi_api_key: str = ""

    # ── LLM sentiment backend (optional) ──────────────────────────────
    # Only used when the `sentiment_backend` setting is "llm". It runs through
    # the local Claude Code CLI subscription (Claude Agent SDK) — no API key.
    # Leave the model blank to use the CLI's default; set it to pin a model.
    anthropic_sentiment_model: str = ""

    # ── Safety ────────────────────────────────────────────────────────
    # The single source of truth for whether real money can move. Even with
    # this true, the trading layer additionally requires a non-paper base URL
    # and an explicit per-session UI confirmation.
    live_trading: bool = False

    # ── Risk parameters ───────────────────────────────────────────────
    max_position_pct: float = 0.10
    max_total_exposure_pct: float = 0.80
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.15

    # ── App ───────────────────────────────────────────────────────────
    database_url: str = "sqlite:///./stock_trader.db"
    watchlist: str = "AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA,AMD,NFLX,SPY"

    @property
    def is_paper(self) -> bool:
        """True when pointed at the paper endpoint (no real money)."""
        return "paper" in self.alpaca_base_url.lower()

    @property
    def has_credentials(self) -> bool:
        return bool(self.apca_api_key_id and self.apca_api_secret_key)

    @property
    def watchlist_symbols(self) -> list[str]:
        return [s.strip().upper() for s in self.watchlist.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
