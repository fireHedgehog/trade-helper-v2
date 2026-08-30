"""Application settings, loaded from environment / backend/.env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Where the SQLite file lives. Relative paths resolve against the repo root.
    database_path: Path = REPO_ROOT / "database" / "trade_helper.sqlite3"

    # Folder holding the ordered *.sql migration files.
    schema_dir: Path = REPO_ROOT / "schema" / "migrations"

    # Frontend origins allowed by CORS (the Vite dev server).
    cors_origins: list[str] = ["http://localhost:5173"]

    # Provider base URLs — used by the credential "Verify" action (and, for
    # OpenAI, by the Macro AI regime feature).
    alpaca_api_base: str = "https://paper-api.alpaca.markets"  # trading API (assets)
    alpaca_data_base: str = "https://data.alpaca.markets"      # market data API (bars)
    fred_api_base: str = "https://api.stlouisfed.org"
    openai_api_base: str = "https://api.openai.com"
    openai_model: str = "gpt-4o-mini"  # cheap model for the Macro AI regime estimate

    # Network timeout (seconds) for verify calls.
    verify_timeout_seconds: float = 10.0

    # ---- Fetch / pacing (docs/draft-design/09-…-audit.md §3) ----
    # Minimum seconds between requests to each provider host (1 in-flight ever).
    alpaca_min_interval_seconds: float = 0.40   # ~150 req/min, under the 200 cap
    fred_min_interval_seconds: float = 0.70     # ~85 req/min, under the 120 cap
    fetch_timeout_seconds: float = 30.0
    fetch_max_retries: int = 4

    # Earliest bar/observation date on a first (full) pull — aligns every
    # family to the Alpaca equity history start.
    history_start_date: str = "2016-01-01"

    # Equity bar feed. The free plan's `iex` feed only archives ~mid-2020 and
    # carries just IEX's ~3% of volume; `sip` (consolidated tape) goes back to
    # 2016 with real volume, but the free plan forbids reading its most recent
    # ~15 min — so SIP requests end at `today - alpaca_sip_end_lag_days`.
    alpaca_price_feed: str = "sip"
    alpaca_sip_end_lag_days: int = 1

    # Trailing window (days) re-fetched every incremental macro/commodity run
    # to pick up FRED revisions.
    fred_revision_lookback_days: int = 90

    def resolved_database_path(self) -> Path:
        path = self.database_path
        if not path.is_absolute():
            path = (REPO_ROOT / path).resolve()
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()
