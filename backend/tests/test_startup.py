"""Phase 5A: production startup fails clearly when required configuration is missing or storage is unusable."""

import os
from pathlib import Path
from typing import Any

import pytest

from app.config import Settings
from app.main import create_app
from app.startup import StartupConfigurationError, check_startup, configuration_problems, storage_problems
from tests.fakes import FakeProvider

ORIGIN = "https://vektor.example"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [n for n in os.environ if n.startswith("VEKTOR_") or n == "ANTHROPIC_API_KEY"]:
        monkeypatch.delenv(name)


def production(tmp_path: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": "production",
        "cors_origins": [ORIGIN],
        "market_data_cache_path": tmp_path / "data" / "market_data.sqlite3",
        "portfolio_db_path": tmp_path / "data" / "portfolios.sqlite3",
        "backtest_db_path": tmp_path / "data" / "backtests.sqlite3",
        **overrides,
    }
    return Settings(_env_file=None, **{key: value for key, value in values.items() if value is not None})


def test_complete_production_configuration_starts(tmp_path: Path) -> None:
    check_startup(production(tmp_path))
    assert (tmp_path / "data").is_dir()


def test_production_requires_explicit_cors_origins(tmp_path: Path) -> None:
    problems = configuration_problems(production(tmp_path, cors_origins=None))
    assert len(problems) == 1 and "VEKTOR_CORS_ORIGINS" in problems[0]


def test_an_explicitly_empty_origin_list_is_accepted(tmp_path: Path) -> None:
    assert configuration_problems(production(tmp_path, cors_origins=[])) == []


def test_production_requires_explicit_database_paths(tmp_path: Path) -> None:
    problems = configuration_problems(production(tmp_path, portfolio_db_path=None, backtest_db_path=None))
    assert any("VEKTOR_PORTFOLIO_DB_PATH" in p for p in problems)
    assert any("VEKTOR_BACKTEST_DB_PATH" in p for p in problems)


def test_the_market_data_cache_path_may_stay_at_its_default(tmp_path: Path) -> None:
    assert configuration_problems(production(tmp_path, market_data_cache_path=None)) == []


def test_anthropic_analysis_requires_a_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (problem,) = configuration_problems(production(tmp_path, ai_provider="anthropic"))
    assert "VEKTOR_AI_API_KEY" in problem and "ANTHROPIC_API_KEY" in problem
    assert configuration_problems(production(tmp_path, ai_provider="anthropic", ai_api_key="sk-ant-x")) == []
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-sdk-env")
    assert configuration_problems(production(tmp_path, ai_provider="anthropic")) == []
