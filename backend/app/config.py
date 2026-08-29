from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEVELOPMENT_CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]


class Settings(BaseSettings):
    """App settings from env vars prefixed VEKTOR_ (or backend/.env)."""

    model_config = SettingsConfigDict(env_prefix="VEKTOR_", env_file=".env", extra="forbid")

    app_name: str = "Vektor"
    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    # Browser origins allowed to call the API: scheme://host[:port], no path.
    cors_origins: list[str] = Field(default_factory=lambda: list(DEVELOPMENT_CORS_ORIGINS))
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
    # Optional AI explanations of backtests (Phase 3A.1). "none" (the default) keeps Vektor fully local and free.
    ai_provider: Literal["none", "anthropic"] = "none"
    ai_model: str = Field(default="claude-opus-5-5", min_length=1, max_length=100)
    # Read from the environment only; never logged or returned. Unset: the SDK falls back to ANTHROPIC_API_KEY.
    ai_api_key: SecretStr | None = None
    ai_timeout_seconds: float = Field(default=120, gt=0, le=600)

    @field_validator("cors_origins")
    @classmethod
    def check_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            if origin != "*" and not _is_origin(origin):
                raise ValueError("each CORS origin must be scheme://host[:port] with http or https and no path")
        return origins


def _is_origin(value: str) -> bool:
    try:
        parts = urlsplit(value)
        port_ok = parts.port is None or parts.port > 0  # .port raises ValueError when out of range
    except ValueError:
        return False
    return (
        port_ok
        and parts.scheme in {"http", "https"}
        and bool(parts.hostname)
        and parts.path == ""
        and not (parts.query or parts.fragment or parts.username or parts.password)
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
