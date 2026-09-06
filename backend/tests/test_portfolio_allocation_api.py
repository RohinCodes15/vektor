from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
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


def test_cash_only_allocation(client: TestClient) -> None:
    portfolio_id = client.post(URL, json={"name": "Cash", "starting_cash": "10"}).json()["id"]
    assert client.get(f"{URL}/{portfolio_id}/allocation").json()["cash_weight_pct"] == "100.0000"


@pytest.mark.parametrize("path", ["allocation"])
def test_unknown_or_invalid_portfolio(client: TestClient, path: str) -> None:
    assert client.get(f"{URL}/{uuid4()}/{path}").status_code == 404
    assert client.get(f"{URL}/not-a-uuid/{path}").status_code == 422

