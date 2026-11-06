from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings from env vars prefixed VEKTOR_ (or backend/.env)."""

    model_config = SettingsConfigDict(env_prefix="VEKTOR_", env_file=".env", extra="forbid")

    app_name: str = "Vektor"
    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    # Paper-only by construction: any other value fails validation at startup.
    trading_mode: Literal["paper"] = "paper"


@lru_cache
def get_settings() -> Settings:
    return Settings()
