import os
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.config import DEVELOPMENT_CORS_ORIGINS, Settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The developer's own VEKTOR_* variables must not change these defaults."""
    for name in [name for name in os.environ if name.startswith("VEKTOR_")]:
        monkeypatch.delenv(name)


def settings(**values: Any) -> Settings:
    return Settings(_env_file=None, **values)


def test_development_keeps_local_frontends_and_docs_and_sets_limits() -> None:
    s = settings()
    assert s.environment == "development"
    assert s.cors_origins == DEVELOPMENT_CORS_ORIGINS and s.docs_enabled
    assert (s.max_request_body_bytes, s.rate_limit_per_minute, s.expensive_rate_limit_per_minute) == (65536, 300, 30)
    assert (s.max_concurrent_expensive_requests, s.max_backtest_range_days) == (4, 7305)
    assert s.market_data_max_concurrent_fetches == 4


def test_production_defaults_to_no_cors_origins_and_no_docs() -> None:
    s = settings(environment="production")
    assert s.cors_origins == [] and s.docs_enabled is False


def test_production_keeps_explicit_https_origins_and_docs() -> None:
    s = settings(environment="production", cors_origins=["https://vektor.example", "http://localhost:3000"],
                 docs_enabled=True)
    assert s.cors_origins == ["https://vektor.example", "http://localhost:3000"] and s.docs_enabled


def test_production_values_from_the_environment_count_as_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VEKTOR_ENVIRONMENT", "production")
    monkeypatch.setenv("VEKTOR_CORS_ORIGINS", '["https://vektor.example"]')
    monkeypatch.setenv("VEKTOR_DOCS_ENABLED", "true")
    s = Settings(_env_file=None)
    assert s.cors_origins == ["https://vektor.example"] and s.docs_enabled


@pytest.mark.parametrize(
    ("origins", "message"),
    [
        (["*"], "wildcard"),
        (["http://vektor.example"], "must use https"),
        (["https://vektor.example", "http://192.168.1.5:3000"], "must use https"),
    ],
)
def test_production_rejects_wildcard_and_plain_http_origins(origins: list[str], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        settings(environment="production", cors_origins=origins)


@pytest.mark.parametrize(
    "origin",
    ["http://localhost:3000/", "https://vektor.example/app", "ftp://vektor.example", "localhost:3000",
     "https://user:pw@vektor.example", "https://vektor.example?x=1", "http://localhost:99999", "https://"],
)
def test_malformed_origins_are_rejected_in_every_environment(origin: str) -> None:
    with pytest.raises(ValidationError, match="scheme://host"):
        settings(cors_origins=[origin])


@pytest.mark.parametrize(
    "bad",
    [
        {"max_request_body_bytes": 100}, {"max_request_body_bytes": 100 * 1024 * 1024},
        {"rate_limit_per_minute": -1}, {"expensive_rate_limit_per_minute": -1},
        {"max_concurrent_expensive_requests": 0}, {"max_backtest_range_days": 10},
        {"max_backtest_range_days": 40_000},
        {"market_data_max_concurrent_fetches": 0}, {"market_data_max_concurrent_fetches": 17},
    ],
)
def test_resource_limits_are_bounded(bad: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        settings(**bad)


def test_zero_turns_rate_limits_off() -> None:
    s = settings(rate_limit_per_minute=0, expensive_rate_limit_per_minute=0)
    assert (s.rate_limit_per_minute, s.expensive_rate_limit_per_minute) == (0, 0)


def test_the_ai_api_key_never_appears_in_settings_output() -> None:
    s = settings(ai_provider="anthropic", ai_api_key="sk-ant-very-secret")
    for rendered in (repr(s), str(s), s.model_dump_json(), str(s.model_dump())):
        assert "sk-ant-very-secret" not in rendered
    assert s.ai_api_key is not None and s.ai_api_key.get_secret_value() == "sk-ant-very-secret"


def test_the_example_env_file_keeps_production_locked_down(monkeypatch: pytest.MonkeyPatch) -> None:
    example = Path(__file__).resolve().parent.parent / ".env.example"
    assert Settings(_env_file=example).cors_origins == DEVELOPMENT_CORS_ORIGINS
    monkeypatch.setenv("VEKTOR_ENVIRONMENT", "production")
    production = Settings(_env_file=example)
    assert production.cors_origins == [] and production.docs_enabled is False
