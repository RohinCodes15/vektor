"""Phase 5A deployment artifacts: the manifests agree with the startup checks, and backups are consistent."""

import os
import sqlite3
import tomllib
from contextlib import closing
from pathlib import Path

import pytest

from app.backup import backup_databases, main
from app.config import Settings
from app.startup import configuration_problems

BACKEND = Path(__file__).resolve().parent.parent
FLY = tomllib.loads((BACKEND / "fly.toml").read_text())
DOCKERFILE = (BACKEND / "Dockerfile").read_text()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [n for n in os.environ if n.startswith("VEKTOR_") or n == "ANTHROPIC_API_KEY"]:
        monkeypatch.delenv(name)


def vektor_env(env: dict[str, str]) -> dict[str, str]:
    return {key.removeprefix("VEKTOR_").lower(): value for key, value in env.items() if key.startswith("VEKTOR_")}


def test_fly_keeps_every_database_on_the_mounted_volume() -> None:
    (mount,) = FLY["mounts"]
    env = FLY["env"]
    for name in ("VEKTOR_PORTFOLIO_DB_PATH", "VEKTOR_BACKTEST_DB_PATH", "VEKTOR_MARKET_DATA_CACHE_PATH"):
        assert Path(env[name]).parent == Path(mount["destination"])


def test_fly_runs_paper_only_production_with_a_health_check() -> None:
    env = FLY["env"]
    assert env["VEKTOR_ENVIRONMENT"] == "production" and env["VEKTOR_TRADING_MODE"] == "paper"
    assert env["VEKTOR_AI_PROVIDER"] == "none"
    service = FLY["http_service"]
    assert service["internal_port"] == 8000 and service["force_https"] is True
    assert [check["path"] for check in service["checks"]] == ["/api/v1/health"]


def test_fly_holds_no_secrets_and_leaves_cors_to_the_operator() -> None:
    assert not any("KEY" in name or "SECRET" in name or "TOKEN" in name for name in FLY["env"])
    # Deliberately unset: startup must fail until the operator names the frontend origin.
    problems = configuration_problems(Settings(_env_file=None, **vektor_env(FLY["env"])))
    assert len(problems) == 1 and "VEKTOR_CORS_ORIGINS" in problems[0]
