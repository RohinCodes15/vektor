from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.market_data.errors import MarketDataUnavailable
from tests.fakes import FakeProvider, make_bar

URL = "/api/v1/portfolios"
YESTERDAY = datetime.now(UTC).date() - timedelta(days=1)


def history(closes: list[float]) -> list[Any]:
    first = YESTERDAY - timedelta(days=len(closes) - 1)
    return [make_bar((first + timedelta(days=i)).isoformat(), close) for i, close in enumerate(closes)]


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider(
        bars_by_symbol={
            "AAPL": history([100 + (3 if i % 2 else 0) + i * 0.1 for i in range(25)] + [100.0]),
            "MSFT": history([50 + (1 if i % 3 else 0) for i in range(25)] + [50.0]),
        }
    )


@pytest.fixture
def client(provider: FakeProvider, tmp_path: Path) -> TestClient:
    settings = Settings(
        environment="test",
        market_data_cache_path=tmp_path / "cache.sqlite3",
        portfolio_db_path=tmp_path / "portfolios.sqlite3",
    )
    return TestClient(create_app(settings, market_data_provider=provider))


@pytest.fixture
def portfolio_id(client: TestClient) -> str:
    portfolio_id: str = client.post(URL, json={"name": "Main", "starting_cash": "1000"}).json()["id"]
    for symbol, quantity in (("AAPL", "6"), ("MSFT", "2")):
        body = {"client_order_id": symbol, "symbol": symbol, "side": "buy", "quantity": quantity}
        assert client.post(f"{URL}/{portfolio_id}/orders", json=body).status_code == 201
    return portfolio_id


def test_allocation_endpoint(client: TestClient, portfolio_id: str) -> None:
    res = client.get(f"{URL}/{portfolio_id}/allocation")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "available" and body["unavailable_reason"] is None
    assert (body["cash"], body["equity"], body["cash_weight_pct"]) == ("300.00", "1000.00", "30.0000")
    assert [(a["symbol"], a["weight_pct"], a["position_weight_pct"], a["stale"]) for a in body["assets"]] == [
        ("AAPL", "60.0000", "85.7143", False),
        ("MSFT", "10.0000", "14.2857", False),
    ]
    assert (body["top_holding_symbol"], body["top_holding_pct"], body["hhi"]) == ("AAPL", "85.7143", "0.7551")


def test_risk_endpoint(client: TestClient, portfolio_id: str) -> None:
    res = client.get(f"{URL}/{portfolio_id}/risk")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "available" and body["observations"] == 25 and body["min_observations"] == 20
    assert body["returns_as_of"] == YESTERDAY.isoformat()
    assert isinstance(body["portfolio_volatility_pct"], str)
    assert [a["symbol"] for a in body["assets"]] == ["AAPL", "MSFT"]
    assert body["assets"][0].keys() == {
        "symbol", "weight_pct", "volatility_pct", "volatility_contribution_pct", "contribution_share_pct",
    }
    assert [(c["symbol_a"], c["symbol_b"]) for c in body["correlations"]] == [("AAPL", "MSFT")]


def test_risk_endpoint_reports_unavailable_for_cash_only(client: TestClient) -> None:
    portfolio_id = client.post(URL, json={"name": "Cash", "starting_cash": "10"}).json()["id"]
    body = client.get(f"{URL}/{portfolio_id}/risk").json()
    assert body["status"] == "unavailable" and body["portfolio_volatility_pct"] is None
    assert body["observations"] == 0 and body["returns_as_of"] is None
    assert client.get(f"{URL}/{portfolio_id}/allocation").json()["cash_weight_pct"] == "100.0000"


@pytest.mark.parametrize("path", ["allocation", "risk"])
def test_unknown_or_invalid_portfolio(client: TestClient, path: str) -> None:
    assert client.get(f"{URL}/{uuid4()}/{path}").status_code == 404
    assert client.get(f"{URL}/not-a-uuid/{path}").status_code == 422


def test_risk_provider_outage_is_503(client: TestClient, provider: FakeProvider, portfolio_id: str) -> None:
    provider.error = MarketDataUnavailable("down")
    res = client.get(f"{URL}/{portfolio_id}/risk")
    assert res.status_code == 503 and res.json().keys() == {"detail"}
