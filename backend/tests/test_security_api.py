"""Phase 4A hardening, exercised through the real app."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.analysis_support import SWING, price_bars
from tests.fakes import FakeProvider

ORIGIN = "http://localhost:3000"
COSTS = {"start": "2024-01-01", "end": "2024-06-28", "starting_cash": "10000"}
BACKTEST = {**COSTS, "symbols": ["AAPL"], "strategy": {"kind": "buy_and_hold"}}
COMPARISON = {**COSTS, "symbol": "AAPL", "strategies": [
    {"kind": "buy_and_hold"}, {"kind": "sma_crossover", "fast_window": 2, "slow_window": 3},
]}
OPTIMIZATION = {**COSTS, "symbol": "AAPL", "objective": "total_return_pct",
                "grid": {"kind": "sma_crossover", "fast_windows": [2], "slow_windows": [3]}}


def make_client(tmp_path: Path, provider: FakeProvider | None = None, **overrides: Any) -> TestClient:
    """Test settings plus overrides; an override of None leaves that setting at its environment default."""
    values: dict[str, Any] = {
        "environment": "test",
        "market_data_cache_path": tmp_path / "cache.sqlite3",
        "portfolio_db_path": tmp_path / "portfolios.sqlite3",
        "backtest_db_path": tmp_path / "backtests.sqlite3",
        "cors_origins": [ORIGIN],
        "ai_provider": "none",
        **overrides,
    }
    settings = Settings(_env_file=None, **{key: value for key, value in values.items() if value is not None})
    app = create_app(settings, market_data_provider=provider or FakeProvider(price_bars(SWING)))
    return TestClient(app, raise_server_exceptions=False)


def test_an_oversize_body_is_rejected_before_any_work(tmp_path: Path) -> None:
    provider = FakeProvider(price_bars(SWING))
    client = make_client(tmp_path, provider, max_request_body_bytes=1024)
    res = client.post("/api/v1/backtests", json={**BACKTEST, "padding": "x" * 2000})
    assert res.status_code == 413 and res.json() == {"detail": "Request body is larger than the 1024-byte limit."}
    assert provider.calls == []


@pytest.mark.parametrize(
    ("path", "body"),
    [("/api/v1/backtests", BACKTEST), ("/api/v1/backtests/comparisons", COMPARISON),
     ("/api/v1/backtests/optimizations", OPTIMIZATION)],
)
def test_date_ranges_over_the_limit_are_rejected_before_fetching(
    tmp_path: Path, path: str, body: dict[str, Any]
) -> None:
    provider = FakeProvider(price_bars(SWING))
    client = make_client(tmp_path, provider, max_backtest_range_days=30)
    res = client.post(path, json={**body, "start": "2024-01-01", "end": "2024-02-01"})
    assert res.status_code == 422
    assert res.json() == {"detail": "The date range spans 31 days; the limit is 30 days (about 0 years). "
                                    "Choose a shorter range."}
    assert provider.calls == []


def test_a_date_range_at_the_limit_runs(tmp_path: Path) -> None:
    provider = FakeProvider(price_bars(SWING))
    client = make_client(tmp_path, provider, max_backtest_range_days=180)
    res = client.post("/api/v1/backtests", json={**BACKTEST, "start": "2024-01-01", "end": "2024-06-29"})
    assert res.status_code == 201 and len(provider.calls) == 1
