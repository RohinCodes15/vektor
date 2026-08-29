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


@pytest.mark.parametrize(
    "origin",
    ["http://localhost:3000/", "https://vektor.example/app", "ftp://vektor.example", "localhost:3000",
     "https://user:pw@vektor.example", "https://vektor.example?x=1", "http://localhost:99999", "https://"],
)
def test_malformed_origins_are_rejected_in_every_environment(origin: str) -> None:
    with pytest.raises(ValidationError, match="scheme://host"):
        settings(cors_origins=[origin])
