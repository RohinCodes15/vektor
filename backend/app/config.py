from functools import lru_cache
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEVELOPMENT_CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "[::1]"}
MIN_OWNER_KEY_LENGTH = 32


class Settings(BaseSettings):
    """App settings from env vars prefixed VEKTOR_ (or backend/.env)."""

    model_config = SettingsConfigDict(env_prefix="VEKTOR_", env_file=".env", extra="forbid")

    app_name: str = "Vektor"
    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    # Browser origins allowed to call the API: scheme://host[:port], no path. Production defaults to none.
    cors_origins: list[str] = Field(default_factory=lambda: list(DEVELOPMENT_CORS_ORIGINS))
    # Interactive API docs (/docs, /redoc, /openapi.json). Production defaults to off.
    docs_enabled: bool = True
    # Paper-only by construction: any other value fails validation at startup.
    trading_mode: Literal["paper"] = "paper"
    # Local SQLite cache for read-only historical prices. Relative paths resolve from the working directory.
    market_data_cache_path: Path = BACKEND_DIR / "data" / "market_data.sqlite3"
    # How long a cached provider response is reused before it is fetched again.
    market_data_cache_ttl_hours: int = Field(default=24, ge=1, le=24 * 365)
    # Provider (Yahoo Finance) requests in flight at once across all API requests (Phase 4B). More wait their turn.
    market_data_max_concurrent_fetches: int = Field(default=4, ge=1, le=16)
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
    # Resource limits (Phase 4A). Rate limits count requests per client IP per minute; 0 turns a limit off.
    max_request_body_bytes: int = Field(default=64 * 1024, ge=1024, le=10 * 1024 * 1024)
    rate_limit_per_minute: int = Field(default=300, ge=0, le=100_000)
    # Backtests, comparisons, optimizations, and AI analysis: every POST under /api/v1/backtests.
    expensive_rate_limit_per_minute: int = Field(default=30, ge=0, le=10_000)
    # Reverse proxies in front of the API that append the client's address to X-Forwarded-For (1 on Fly.io).
    # 0 (the default) keys rate limits on the TCP peer. Entries left of the trusted ones are client-written and ignored.
    trusted_proxy_hops: int = Field(default=0, ge=0, le=5)
    max_concurrent_expensive_requests: int = Field(default=4, ge=1, le=64)
    # Longest start-to-end span a backtest, comparison, or optimization may request (about 20 years).
    max_backtest_range_days: int = Field(default=7305, ge=30, le=36_525)
    # Public deployments (Phase 5F): paper portfolio writes and the listing of every stored backtest need the owner
    # key, because the API has no user accounts. Production defaults to on.
    public_mode: bool = False
    # Sent as the X-Vektor-Owner-Key header to unlock owner-only requests. Environment only (a host secret); never
    # logged or returned. Unset in public mode: nobody can write portfolios.
    owner_key: SecretStr | None = None

    @field_validator("owner_key")
    @classmethod
    def check_owner_key(cls, key: SecretStr | None) -> SecretStr | None:
        if key is not None and len(key.get_secret_value()) < MIN_OWNER_KEY_LENGTH:
            raise ValueError(f"the owner key must be at least {MIN_OWNER_KEY_LENGTH} characters (random)")
        return key

    @field_validator("cors_origins")
    @classmethod
    def check_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            if origin != "*" and not _is_origin(origin):
                raise ValueError("each CORS origin must be scheme://host[:port] with http or https and no path")
        return origins

    @model_validator(mode="after")
    def production_defaults(self) -> Self:
        """Production locks down what development leaves open, unless a value is set explicitly."""
        if self.environment != "production":
            return self
        defaulted = {"cors_origins", "docs_enabled", "public_mode"} - self.model_fields_set
        if "cors_origins" in defaulted:
            self.cors_origins = []
        if "docs_enabled" in defaulted:
            self.docs_enabled = False
        if "public_mode" in defaulted:
            self.public_mode = True
        # Assignment marks a field as set; keep model_fields_set meaning "set by the operator" (app.startup uses it).
        self.model_fields_set.difference_update(defaulted)
        for origin in self.cors_origins:
            if origin == "*":
                raise ValueError("a wildcard CORS origin is not allowed in production: list the exact origins")
            parts = urlsplit(origin)
            if parts.scheme != "https" and parts.hostname not in {host.strip("[]") for host in LOOPBACK_HOSTS}:
                raise ValueError("production CORS origins must use https (plain http is allowed for localhost only)")
        return self


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
