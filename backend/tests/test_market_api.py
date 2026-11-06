from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.market_data.errors import InvalidMarketData, MarketDataNotFound, MarketDataUnavailable
from app.main import create_app
from tests.fakes import FakeProvider, make_bar

URL = "/api/v1/market/history"
PARAMS = {"symbol": "aapl", "start": "2024-01-01", "end": "2024-01-31"}


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def client(provider: FakeProvider, tmp_path: Path) -> TestClient:
    settings = Settings(environment="test", market_data_cache_path=tmp_path / "cache.sqlite3")
    return TestClient(create_app(settings, market_data_provider=provider))


def test_returns_normalized_daily_history(client: TestClient, provider: FakeProvider) -> None:
    res = client.get(URL, params=PARAMS)
    assert res.status_code == 200
    body = res.json()
    assert body.keys() == {"symbol", "interval", "start", "end", "currency", "source", "cached", "fetched_at", "bars"}
    assert (body["symbol"], body["interval"], body["start"], body["end"]) == ("AAPL", "1d", "2024-01-01", "2024-01-31")
    assert (body["currency"], body["source"], body["cached"]) == ("USD", "yahoo_finance", False)
    assert datetime.fromisoformat(body["fetched_at"]).tzinfo is not None
    assert body["bars"][0] == {"date": "2024-01-02", "open": 10.0, "high": 12.0, "low": 9.5, "close": 11.0,
                               "adjusted_close": 11.0, "volume": 1000}
    assert [bar["date"] for bar in body["bars"]] == ["2024-01-02", "2024-01-03"]
    assert provider.calls[0][0] == "AAPL"


def test_repeat_requests_are_served_from_the_cache(client: TestClient, provider: FakeProvider) -> None:
    first = client.get(URL, params=PARAMS).json()
    second = client.get(URL, params=PARAMS).json()
    assert len(provider.calls) == 1
    assert second["cached"] is True and second["fetched_at"] == first["fetched_at"]
    assert second["bars"] == first["bars"]


def test_cache_persists_across_app_instances(provider: FakeProvider, tmp_path: Path) -> None:
    settings = Settings(environment="test", market_data_cache_path=tmp_path / "cache.sqlite3")
    TestClient(create_app(settings, market_data_provider=provider)).get(URL, params=PARAMS)
    res = TestClient(create_app(settings, market_data_provider=provider)).get(URL, params=PARAMS)
    assert res.json()["cached"] is True and len(provider.calls) == 1


def test_accepts_an_explicit_daily_interval(client: TestClient) -> None:
    assert client.get(URL, params={**PARAMS, "interval": "1d"}).status_code == 200


@pytest.mark.parametrize(
    ("params", "detail"),
    [
        ({"symbol": "AAPL", "start": "2024-01-01"}, "end: Field required"),
        ({**PARAMS, "symbol": "AA PL"}, "symbol: symbol must be 1-15 letters, digits, '.', '-' or '=', optionally prefixed with '^'"),
        ({**PARAMS, "start": "2024-02-01"}, "start must be on or before end"),
        ({**PARAMS, "start": "01/02/2024"}, "start: Input should be a valid date"),
        ({**PARAMS, "interval": "1h"}, "interval: Input should be '1d'"),
        ({**PARAMS, "api_key": "x"}, "api_key: Extra inputs are not permitted"),
    ],
)
def test_invalid_requests_return_422_without_calling_the_provider(
    client: TestClient, provider: FakeProvider, params: dict[str, str], detail: str
) -> None:
    res = client.get(URL, params=params)
    assert res.status_code == 422
    assert res.json()["detail"].startswith(detail)
    assert provider.calls == []


def test_future_start_dates_are_rejected(client: TestClient) -> None:
    tomorrow = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
    res = client.get(URL, params={**PARAMS, "start": tomorrow, "end": tomorrow})
    assert res.status_code == 422 and res.json() == {"detail": "start cannot be in the future"}


def test_no_bars_returns_404(client: TestClient, provider: FakeProvider) -> None:
    provider.bars = [make_bar("2023-06-01")]
    res = client.get(URL, params=PARAMS)
    assert res.status_code == 404
    assert res.json() == {"detail": "No daily price history found for AAPL between 2024-01-01 and 2024-01-31. "
                                    "Check the symbol or widen the date range."}


@pytest.mark.parametrize(
    ("error", "status"),
    [(MarketDataNotFound("none"), 404), (InvalidMarketData("Provider returned duplicate bars for 2024-01-02."), 502),
     (MarketDataUnavailable("Yahoo Finance could not be reached. Try again later."), 503)],
)
def test_provider_errors_return_their_status_and_message(
    client: TestClient, provider: FakeProvider, error: Exception, status: int
) -> None:
    provider.error = error
    res = client.get(URL, params=PARAMS)
    assert res.status_code == status and res.json() == {"detail": str(error)}


def test_market_data_is_read_only(client: TestClient) -> None:
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)(URL, params=PARAMS).status_code == 405


def test_openapi_documents_the_endpoint_and_errors(client: TestClient) -> None:
    operation = client.get("/openapi.json").json()["paths"][URL]["get"]
    assert {p["name"] for p in operation["parameters"]} == {"symbol", "start", "end", "interval"}
    assert {"200", "404", "422", "502", "503"} <= operation["responses"].keys()


def test_health_is_unchanged(client: TestClient) -> None:
    res = client.get("/api/v1/health")
    assert res.status_code == 200 and res.json()["trading_mode"] == "paper"
    assert res.json().keys() == {"status", "app", "version", "environment", "trading_mode"}
