from datetime import date, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.contracts import PriceBar
from app.main import create_app
from app.market_data.errors import InvalidMarketData, MarketDataUnavailable
from tests.fakes import FakeProvider

URL = "/api/v1/backtests"
FIRST_DAY = date(2024, 1, 2)
BODY: dict[str, Any] = {
    "symbols": ["aapl"], "start": "2024-01-01", "end": "2024-06-28", "starting_cash": "1000",
    "strategy": {"kind": "buy_and_hold"}, "fee_per_trade": "1", "slippage_bps": "10",
}


def price_bars(closes: list[float]) -> list[PriceBar]:
    return [
        PriceBar(date=FIRST_DAY + timedelta(days=i), open=c, high=c + 1, low=c - 1, close=c, adjusted_close=c,
                 volume=1000)
        for i, c in enumerate(closes)
    ]


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider(price_bars([10, 10, 12, 11]))


@pytest.fixture
def client(provider: FakeProvider, tmp_path: Path) -> TestClient:
    settings = Settings(
        environment="test",
        market_data_cache_path=tmp_path / "cache.sqlite3",
        portfolio_db_path=tmp_path / "portfolios.sqlite3",
        backtest_db_path=tmp_path / "backtests.sqlite3",
    )
    return TestClient(create_app(settings, market_data_provider=provider))


def test_run_returns_the_stored_backtest_with_money_as_strings(client: TestClient) -> None:
    res = client.post(URL, json=BODY)
    assert res.status_code == 201
    body = res.json()
    assert body.keys() == {
        "id", "mode", "currency", "config", "created_at", "source", "bars", "first_date", "last_date", "metrics",
        "warnings", "equity_curve", "trades", "rejected_orders", "open_positions",
    }
    assert (body["mode"], body["currency"], body["bars"]) == ("paper", "USD", 4)
    assert body["config"]["symbols"] == ["AAPL"] and body["config"]["fee_per_trade"] == "1.00"
    # Filled at day 2's open 10 plus 10 bp slippage = 10.01: 99 shares (990.99 + 1.00 fee).
    assert body["trades"] == [{
        "symbol": "AAPL", "side": "buy", "signal_date": "2024-01-02", "fill_date": "2024-01-03", "quantity": 99,
        "price": "10.0100", "notional": "990.99", "fee": "1.00", "realized_pnl": None,
    }]
    assert body["equity_curve"][-1] == {
        "date": "2024-01-05", "cash": "8.01", "positions_value": "1089.00", "equity": "1097.01",
        "drawdown_pct": "-8.2775",  # 1097.01 / 1196.01 peak - 1
    }
    assert body["metrics"]["total_fees"] == "1.00" and body["metrics"]["total_return_pct"] == "9.7010"
    assert client.get(f"{URL}/{body['id']}").json() == body


def test_list_returns_summaries(client: TestClient) -> None:
    created = client.post(URL, json=BODY).json()
    listed = client.get(URL).json()
    assert [item["id"] for item in listed] == [created["id"]]
    assert listed[0].keys() == {"id", "created_at", "config", "bars", "first_date", "last_date", "metrics"}
    assert listed[0]["metrics"] == created["metrics"]


def test_empty_list(client: TestClient) -> None:
    assert client.get(URL).json() == []


def test_unknown_and_invalid_ids(client: TestClient) -> None:
    missing = uuid4()
    res = client.get(f"{URL}/{missing}")
    assert (res.status_code, res.json()) == (404, {"detail": f"Backtest {missing} not found"})
    assert client.get(f"{URL}/not-a-uuid").status_code == 422


def test_invalid_requests_return_a_readable_error(client: TestClient) -> None:
    res = client.post(URL, json={**BODY, "strategy": {"kind": "sma_crossover", "fast_window": 9, "slow_window": 5}})
    assert res.status_code == 422
    assert res.json() == {"detail": "strategy.sma_crossover: fast_window must be smaller than slow_window"}
    assert client.post(URL, json={**BODY, "broker_api_key": "x"}).status_code == 422


def test_too_little_history_is_unprocessable_and_not_stored(client: TestClient) -> None:
    res = client.post(URL, json={**BODY, "strategy": {"kind": "rsi", "period": 5}})
    assert res.status_code == 422
    assert "Not enough history: rsi needs at least 7 trading days" in res.json()["detail"]
    assert client.get(URL).json() == []


def test_unknown_symbol_is_unprocessable(client: TestClient, provider: FakeProvider) -> None:
    provider.bars = []
    res = client.post(URL, json=BODY)
    assert res.status_code == 422 and "No daily history for AAPL" in res.json()["detail"]


@pytest.mark.parametrize(
    ("error", "status"), [(InvalidMarketData("Provider returned bad bars"), 502), (MarketDataUnavailable("Down"), 503)]
)
def test_provider_failures_map_to_gateway_errors(
    client: TestClient, provider: FakeProvider, error: Exception, status: int
) -> None:
    provider.error = error
    res = client.post(URL, json=BODY)
    assert res.status_code == status and set(res.json()) == {"detail"}
    assert client.get(URL).json() == []


def test_endpoints_are_documented_under_v1(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert set(paths[URL]) == {"get", "post"}
    assert set(paths[f"{URL}/{{backtest_id}}"]) == {"get"}


@pytest.mark.parametrize("symbols", [[{"ticker": "AAPL"}], [["AAPL"]]])
def test_non_string_symbols_are_unprocessable_not_a_server_error(client: TestClient, symbols: list[Any]) -> None:
    res = client.post(URL, json={**BODY, "symbols": symbols})
    assert res.status_code == 422
    assert "valid string" in res.json()["detail"]


def test_a_short_backtest_with_a_huge_gain_reports_a_null_annualized_return(
    client: TestClient, provider: FakeProvider
) -> None:
    provider.bars = [
        PriceBar(date=FIRST_DAY, open=10, high=11, low=9, close=10, adjusted_close=10, volume=1000),
        PriceBar(date=FIRST_DAY + timedelta(days=1), open=10, high=14, low=9, close=13, adjusted_close=13, volume=1000),
    ]
    res = client.post(URL, json=BODY)
    assert res.status_code == 201
    metrics = res.json()["metrics"]
    # 99 shares bought at 10.01 + 1.00 fee, marked at 13: equity 1295.01.
    assert (metrics["final_equity"], metrics["total_return_pct"], metrics["annualized_return_pct"]) == (
        "1295.01", "29.5010", None,
    )
    assert any(w.startswith("Annualized return is too large to report") for w in res.json()["warnings"])
