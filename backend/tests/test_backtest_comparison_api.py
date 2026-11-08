from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.contracts import PriceBar
from app.main import create_app
from app.market_data.errors import MarketDataUnavailable
from tests.fakes import FakeProvider

URL = "/api/v1/backtests/comparisons"
FIRST_DAY = date(2024, 1, 2)
CLOSES = [10, 11, 12, 11, 10, 9, 10, 12, 13, 12, 11, 10, 11, 12, 14]
STRATEGIES: list[dict[str, Any]] = [
    {"kind": "buy_and_hold"},
    {"kind": "sma_crossover", "fast_window": 2, "slow_window": 3},
    {"kind": "rsi", "period": 2, "oversold": "40", "overbought": "60"},
]
BODY: dict[str, Any] = {
    "symbol": "aapl", "start": "2024-01-01", "end": "2024-06-28", "starting_cash": "1000",
    "strategies": STRATEGIES, "fee_per_trade": "1", "fee_bps": "2", "slippage_bps": "10",
}


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider([
        PriceBar(date=FIRST_DAY + timedelta(days=i), open=c, high=c + 1, low=c - 1, close=c, adjusted_close=c,
                 volume=1000)
        for i, c in enumerate(CLOSES)
    ])


@pytest.fixture
def client(provider: FakeProvider, tmp_path: Path) -> TestClient:
    settings = Settings(
        environment="test",
        market_data_cache_path=tmp_path / "cache.sqlite3",
        portfolio_db_path=tmp_path / "portfolios.sqlite3",
        backtest_db_path=tmp_path / "backtests.sqlite3",
    )
    return TestClient(create_app(settings, market_data_provider=provider))


def test_comparison_aligns_every_curve_to_the_shared_dates(client: TestClient) -> None:
    res = client.post(URL, json=BODY)
    assert res.status_code == 200
    body = res.json()
    assert (body["mode"], body["currency"], body["bars"], body["first_date"]) == ("paper", "USD", 15, "2024-01-02")
    assert body["dates"][-1] == body["last_date"] == "2024-01-16" and len(body["dates"]) == 15
    assert [r["status"] for r in body["results"]] == ["available"] * 3
    assert all(len(r["equity"]) == 15 and r["equity"][0] == "1000.00" for r in body["results"])
    assert [r["strategy"]["kind"] for r in body["results"]] == ["buy_and_hold", "sma_crossover", "rsi"]
    assert "not guaranteed" in body["disclaimer"]


def test_each_result_matches_a_standalone_backtest_with_the_same_settings(client: TestClient) -> None:
    body = client.post(URL, json=BODY).json()
    settings = {k: v for k, v in BODY.items() if k not in ("symbol", "strategies")}
    for result in body["results"]:
        alone = client.post("/api/v1/backtests", json={**settings, "symbols": ["AAPL"], "strategy": result["strategy"]})
        alone_body = alone.json()
        assert result["metrics"] == alone_body["metrics"] and result["warnings"] == alone_body["warnings"]
        assert result["equity"] == [point["equity"] for point in alone_body["equity_curve"]]
    assert any(r["metrics"]["trades"] > 1 for r in body["results"])  # the active strategies really traded


def test_differences_are_against_the_first_strategy_and_leaders_name_the_best(client: TestClient) -> None:
    body = client.post(URL, json=BODY).json()
    base, *_ = results = body["results"]
    assert set(base["vs_baseline"].values()) <= {"0.0000", None}
    for result in results:
        mine, theirs = result["metrics"]["total_return_pct"], base["metrics"]["total_return_pct"]
        assert float(result["vs_baseline"]["total_return_pct"]) == pytest.approx(float(mine) - float(theirs))
    returns = [float(r["metrics"]["total_return_pct"]) for r in results]
    by_metric = {leader["metric"]: leader for leader in body["leaders"]}
    assert len(by_metric) == 6
    assert by_metric["total_return_pct"]["leaders"] == [returns.index(max(returns))]


def test_a_strategy_without_enough_history_is_unavailable_not_an_error(client: TestClient) -> None:
    strategies = [{"kind": "sma_crossover", "fast_window": 20, "slow_window": 50}, *STRATEGIES[:2]]
    body = client.post(URL, json={**BODY, "strategies": strategies}).json()
    first, *rest = body["results"]
    assert (first["status"], first["metrics"], first["equity"], first["vs_baseline"]) == (
        "unavailable", None, None, None,
    )
    assert "Not enough history: sma_crossover needs at least 52 trading days" in first["unavailable_reason"]
    # The baseline is unavailable, so nothing is measured against it; leaders still compare the others.
    assert [r["vs_baseline"] for r in rest] == [None, None]
    assert all(0 not in leader["leaders"] for leader in body["leaders"])


def test_comparison_is_deterministic_and_not_stored(client: TestClient) -> None:
    assert client.post(URL, json=BODY).json() == client.post(URL, json=BODY).json()
    assert client.get("/api/v1/backtests").json() == []


def test_invalid_requests_return_a_readable_error(client: TestClient) -> None:
    res = client.post(URL, json={**BODY, "strategies": [STRATEGIES[0]] * 2})
    assert res.status_code == 422 and "strategies must not repeat" in res.json()["detail"]
    assert client.post(URL, json={**BODY, "strategies": STRATEGIES * 2}).status_code == 422
    assert client.post(URL, json={**BODY, "broker_api_key": "x"}).status_code == 422


def test_unknown_symbol_and_provider_failures(client: TestClient, provider: FakeProvider) -> None:
    provider.bars = []
    res = client.post(URL, json=BODY)
    assert res.status_code == 422 and "No daily history for AAPL" in res.json()["detail"]
    provider.error = MarketDataUnavailable("Down")
    assert client.post(URL, json=BODY).status_code == 503


def test_endpoint_is_documented_under_v1(client: TestClient) -> None:
    assert set(client.get("/openapi.json").json()["paths"][URL]) == {"post"}
