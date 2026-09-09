from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """App settings from env vars prefixed VEKTOR_ (or backend/.env)."""

    model_config = SettingsConfigDict(env_prefix="VEKTOR_", env_file=".env", extra="forbid")

    app_name: str = "Vektor"
    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    # Paper-only by construction: any other value fails validation at startup.
    trading_mode: Literal["paper"] = "paper"
    # Local SQLite cache for read-only historical prices. Relative paths resolve from the working directory.
    market_data_cache_path: Path = BACKEND_DIR / "data" / "market_data.sqlite3"
    # How long a cached provider response is reused before it is fetched again.
    market_data_cache_ttl_hours: int = Field(default=24, ge=1, le=24 * 365)
    # Paper portfolios, positions, and transactions. Kept apart from the disposable market data cache.
    portfolio_db_path: Path = BACKEND_DIR / "data" / "portfolios.sqlite3"
    # Completed backtest results, stored whole so they can be retrieved later.
    backtest_db_path: Path = BACKEND_DIR / "data" / "backtests.sqlite3"


@lru_cache
def get_settings() -> Settings:
    return Settings()
