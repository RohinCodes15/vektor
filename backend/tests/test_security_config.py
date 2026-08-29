import os
from typing import Any

import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The developer's own VEKTOR_* variables must not change these defaults."""
    for name in [name for name in os.environ if name.startswith("VEKTOR_")]:
        monkeypatch.delenv(name)


def settings(**values: Any) -> Settings:
    return Settings(_env_file=None, **values)


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
