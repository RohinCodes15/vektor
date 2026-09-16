from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.contracts import PriceBar
from app.main import create_app
from app.market_data.errors import InvalidMarketData, MarketDataUnavailable
from tests.fakes import FakeProvider, make_bar

URL = "/api/v1/portfolios"
YESTERDAY = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider([make_bar(YESTERDAY, 100.25)])


@pytest.fixture
def client(provider: FakeProvider, tmp_path: Path) -> TestClient:
    settings = Settings(
        environment="test",
        market_data_cache_path=tmp_path / "cache.sqlite3",
        portfolio_db_path=tmp_path / "portfolios.sqlite3",
    )
    return TestClient(create_app(settings, market_data_provider=provider))


@pytest.fixture
def portfolio(client: TestClient) -> dict[str, Any]:
    res = client.post(URL, json={"name": "Main", "starting_cash": "1000"})
    assert res.status_code == 201
    return res.json()


def reprice(provider: FakeProvider, tmp_path: Path, bars: list[PriceBar]) -> None:
    """New closes, as the next day's refetch would bring; completed-day prices are otherwise served from the cache."""
    provider.bars = bars
    (tmp_path / "cache.sqlite3").unlink()


def submit(client: TestClient, portfolio_id: str, **overrides: object) -> Any:
    body = {"client_order_id": "o-1", "symbol": "aapl", "side": "buy", "quantity": "2", **overrides}
    return client.post(f"{URL}/{portfolio_id}/orders", json=body)


def test_create_returns_the_portfolio_with_money_as_strings(portfolio: dict[str, Any]) -> None:
    assert portfolio.keys() == {
        "id", "name", "mode", "currency", "starting_cash", "cash", "realized_pnl", "created_at", "updated_at",
    }
    assert (portfolio["name"], portfolio["mode"], portfolio["currency"]) == ("Main", "paper", "USD")
    assert (portfolio["starting_cash"], portfolio["cash"], portfolio["realized_pnl"]) == ("1000.00", "1000.00", "0.00")


def test_crud_round_trip(client: TestClient, portfolio: dict[str, Any]) -> None:
    pid = portfolio["id"]
    assert client.get(f"{URL}/{pid}").json() == portfolio
    assert client.get(URL).json() == [portfolio]
    renamed = client.patch(f"{URL}/{pid}", json={"name": "Renamed"})
    assert renamed.status_code == 200 and renamed.json()["name"] == "Renamed"
    assert renamed.json()["cash"] == "1000.00"
    deleted = client.delete(f"{URL}/{pid}")
    assert deleted.status_code == 204 and deleted.content == b""
    assert client.get(f"{URL}/{pid}").status_code == 404
    assert client.get(URL).json() == []


def test_portfolios_persist_across_app_instances(provider: FakeProvider, tmp_path: Path) -> None:
    settings = Settings(environment="test", portfolio_db_path=tmp_path / "p.sqlite3",
                        market_data_cache_path=tmp_path / "c.sqlite3")
    created = TestClient(create_app(settings, market_data_provider=provider)).post(
        URL, json={"name": "Kept", "starting_cash": 10}
    ).json()
    assert TestClient(create_app(settings, market_data_provider=provider)).get(f"{URL}/{created['id']}").json() == created


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"name": "x", "starting_cash": "0"}, "starting_cash: Input should be greater than 0"),
        ({"name": "x", "starting_cash": "1.001"}, "starting_cash: Decimal input should have no more than 2 decimal places"),
        ({"name": "   ", "starting_cash": "1"}, "name: String should have at least 1 character"),
        ({"starting_cash": "1"}, "name: Field required"),
        ({"name": "x", "starting_cash": "1", "cash": "5"}, "cash: Extra inputs are not permitted"),
    ],
)
def test_create_validates_input(client: TestClient, body: dict[str, str], detail: str) -> None:
    res = client.post(URL, json=body)
    assert res.status_code == 422 and res.json() == {"detail": detail}


def test_update_cannot_change_cash(client: TestClient, portfolio: dict[str, Any]) -> None:
    res = client.patch(f"{URL}/{portfolio['id']}", json={"name": "x", "cash": "1000000"})
    assert res.status_code == 422 and res.json() == {"detail": "cash: Extra inputs are not permitted"}
    assert client.get(f"{URL}/{portfolio['id']}").json()["cash"] == "1000.00"


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", ""), ("patch", ""), ("delete", ""), ("get", "/holdings"), ("get", "/transactions"), ("post", "/orders")],
)
def test_unknown_portfolio_returns_404(client: TestClient, method: str, path: str) -> None:
    missing = uuid4()
    body = {"name": "x"} if method == "patch" else {
        "client_order_id": "o", "symbol": "AAPL", "side": "buy", "quantity": "1"
    }
    res = client.request(method, f"{URL}/{missing}{path}", json=body if method in {"patch", "post"} else None)
    assert res.status_code == 404 and res.json() == {"detail": f"Portfolio {missing} not found."}


def test_malformed_portfolio_id_returns_422(client: TestClient) -> None:
    res = client.get(f"{URL}/not-a-uuid")
    assert res.status_code == 422 and res.json()["detail"].startswith("portfolio_id: Input should be a valid UUID")


def test_buy_then_sell_round_trip(
    client: TestClient, provider: FakeProvider, portfolio: dict[str, Any], tmp_path: Path
) -> None:
    pid = portfolio["id"]
    bought = submit(client, pid, quantity="4")
    assert bought.status_code == 201
    transaction = bought.json()
    assert transaction.keys() == {
        "id", "portfolio_id", "client_order_id", "symbol", "side", "quantity", "price", "price_date", "notional",
        "realized_pnl", "executed_at",
    }
    assert (transaction["symbol"], transaction["quantity"], transaction["price"], transaction["notional"]) == (
        "AAPL", "4", "100.2500", "401.00",
    )
    assert (transaction["price_date"], transaction["realized_pnl"], transaction["portfolio_id"]) == (
        YESTERDAY, None, pid,
    )

    reprice(provider, tmp_path, [make_bar(YESTERDAY, 110.0)])
    sold = submit(client, pid, client_order_id="o-2", side="sell", quantity="1.5").json()
    assert (sold["notional"], sold["realized_pnl"]) == ("165.00", "14.62")  # basis 401.00 * 1.5/4 = 150.375 -> 150.38

    after = client.get(f"{URL}/{pid}").json()
    assert (after["cash"], after["realized_pnl"]) == ("764.00", "14.62")
    history = client.get(f"{URL}/{pid}/transactions").json()
    assert [t["client_order_id"] for t in history] == ["o-1", "o-2"]


def test_holdings_endpoint(
    client: TestClient, provider: FakeProvider, portfolio: dict[str, Any], tmp_path: Path
) -> None:
    pid = portfolio["id"]
    submit(client, pid, quantity="4")
    reprice(provider, tmp_path, [make_bar(YESTERDAY, 110.0)])
    body = client.get(f"{URL}/{pid}/holdings").json()
    assert body.keys() == {
        "portfolio_id", "currency", "cash", "positions_value", "equity", "unrealized_pnl", "realized_pnl",
        "cash_allocation_pct", "valued_at", "holdings",
    }
    assert (body["cash"], body["positions_value"], body["equity"]) == ("599.00", "440.00", "1039.00")
    assert (body["unrealized_pnl"], body["realized_pnl"], body["cash_allocation_pct"]) == ("39.00", "0.00", "57.65")
    assert body["holdings"] == [{
        "symbol": "AAPL", "quantity": "4", "cost_basis": "401.00", "last_price": "110.0000", "price_date": YESTERDAY,
        "market_value": "440.00", "unrealized_pnl": "39.00", "allocation_pct": "42.35",
    }]


def test_holdings_with_missing_market_data_are_null_not_guessed(
    client: TestClient, provider: FakeProvider, portfolio: dict[str, Any], tmp_path: Path
) -> None:
    submit(client, portfolio["id"])
    reprice(provider, tmp_path, [])
    body = client.get(f"{URL}/{portfolio['id']}/holdings").json()
    assert (body["equity"], body["positions_value"], body["unrealized_pnl"], body["cash_allocation_pct"]) == (
        None, None, None, None,
    )
    assert body["holdings"][0]["market_value"] is None and body["holdings"][0]["quantity"] == "2"


def test_insufficient_funds_is_rejected(client: TestClient, portfolio: dict[str, Any]) -> None:
    res = submit(client, portfolio["id"], quantity="10")
    assert res.status_code == 422
    assert res.json() == {
        "detail": "Insufficient cash: buying 10 AAPL at 100.2500 costs 1002.50, available cash is 1000.00."
    }
    assert client.get(f"{URL}/{portfolio['id']}").json()["cash"] == "1000.00"


def test_overselling_is_rejected(client: TestClient, portfolio: dict[str, Any]) -> None:
    submit(client, portfolio["id"])
    res = submit(client, portfolio["id"], client_order_id="o-2", side="sell", quantity="2.5")
    assert res.status_code == 422 and res.json() == {"detail": "Cannot sell 2.5 AAPL: the portfolio holds 2."}
    never_held = submit(client, portfolio["id"], client_order_id="o-3", side="sell", symbol="MSFT")
    assert never_held.status_code == 422 and "holds none" in never_held.json()["detail"]
    assert len(client.get(f"{URL}/{portfolio['id']}/transactions").json()) == 1


def test_missing_market_data_rejects_the_order(
    client: TestClient, provider: FakeProvider, portfolio: dict[str, Any]
) -> None:
    provider.bars = []
    res = submit(client, portfolio["id"], symbol="ZZZZ")
    assert res.status_code == 422
    assert res.json() == {
        "detail": "No daily close for ZZZZ in the 14 days before today. Check the symbol. The order was not executed."
    }
    assert client.get(f"{URL}/{portfolio['id']}/transactions").json() == []


@pytest.mark.parametrize(
    ("error", "status"), [(MarketDataUnavailable("Yahoo down"), 503), (InvalidMarketData("Bad bar"), 502)]
)
def test_provider_failures_reject_the_order(
    client: TestClient, provider: FakeProvider, portfolio: dict[str, Any], error: Exception, status: int
) -> None:
    provider.error = error
    res = submit(client, portfolio["id"])
    assert res.status_code == status and res.json() == {"detail": str(error)}
    assert client.get(f"{URL}/{portfolio['id']}").json()["cash"] == "1000.00"


@pytest.mark.parametrize(
    ("overrides", "detail"),
    [
        ({"symbol": "^GSPC"}, "symbol: symbol must be a ticker of 1-15 letters, digits, '.' or '-'"),
        ({"symbol": "AA PL"}, "symbol: symbol must be a ticker of 1-15 letters, digits, '.' or '-'"),
        ({"quantity": "0"}, "quantity: Input should be greater than 0"),
        ({"quantity": "-1"}, "quantity: Input should be greater than 0"),
        ({"side": "short"}, "side: Input should be 'buy' or 'sell'"),
        ({"type": "limit"}, "type: Extra inputs are not permitted"),
        ({"client_order_id": ""}, "client_order_id: String should have at least 1 character"),
    ],
)
def test_invalid_orders_return_422_without_calling_the_provider(
    client: TestClient, provider: FakeProvider, portfolio: dict[str, Any], overrides: dict[str, str], detail: str
) -> None:
    res = submit(client, portfolio["id"], **overrides)
    assert res.status_code == 422 and res.json() == {"detail": detail}
    assert provider.calls == []


def test_duplicate_submission_executes_once(client: TestClient, portfolio: dict[str, Any]) -> None:
    first = submit(client, portfolio["id"])
    replay = submit(client, portfolio["id"])
    assert (first.status_code, replay.status_code) == (201, 200)
    assert replay.json() == first.json()
    assert client.get(f"{URL}/{portfolio['id']}").json()["cash"] == "799.50"
    conflict = submit(client, portfolio["id"], quantity="3")
    assert conflict.status_code == 409
    assert conflict.json() == {"detail": "client_order_id 'o-1' was already used for a different order in this portfolio."}


def test_delete_removes_holdings_and_history(client: TestClient, portfolio: dict[str, Any]) -> None:
    submit(client, portfolio["id"])
    client.delete(f"{URL}/{portfolio['id']}")
    assert client.get(f"{URL}/{portfolio['id']}/transactions").status_code == 404


def test_openapi_documents_the_portfolio_endpoints(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert set(paths[URL]) == {"get", "post"}
    assert set(paths[f"{URL}/{{portfolio_id}}"]) == {"get", "patch", "delete"}
    assert set(paths[f"{URL}/{{portfolio_id}}/holdings"]) == {"get"}
    assert set(paths[f"{URL}/{{portfolio_id}}/transactions"]) == {"get"}
    orders = paths[f"{URL}/{{portfolio_id}}/orders"]
    assert set(orders) == {"post"}
    assert {"200", "201", "404", "409", "422", "502", "503"} <= orders["post"]["responses"].keys()


def test_existing_endpoints_are_unchanged(client: TestClient) -> None:
    assert client.get("/api/v1/health").json()["trading_mode"] == "paper"
    history = client.get("/api/v1/market/history", params={"symbol": "AAPL", "start": YESTERDAY, "end": YESTERDAY})
    assert history.status_code == 200 and history.json()["bars"][0]["close"] == 100.25


def test_new_portfolio_has_an_initial_snapshot_and_analytics(client: TestClient, portfolio: dict[str, Any]) -> None:
    pid = portfolio["id"]
    (initial,) = client.get(f"{URL}/{pid}/equity-history").json()
    assert initial.keys() == {
        "id", "portfolio_id", "taken_at", "cash", "positions_value", "equity", "net_deposits", "realized_pnl",
        "unrealized_pnl", "prices_as_of",
    }
    assert (initial["equity"], initial["positions_value"], initial["net_deposits"], initial["prices_as_of"]) == (
        "1000.00", "0.00", "1000.00", None,
    )
    analytics = client.get(f"{URL}/{pid}/analytics").json()
    assert analytics.keys() == {
        "portfolio_id", "currency", "as_of", "snapshots", "daily_observations", "equity", "net_deposits",
        "realized_pnl", "unrealized_pnl", "total_return_pct", "latest_daily_return_pct", "volatility_pct",
        "max_drawdown_pct", "sharpe_ratio",
    }
    assert (analytics["snapshots"], analytics["equity"], analytics["total_return_pct"]) == (1, "1000.00", "0.0000")
    assert analytics["as_of"] == initial["taken_at"]
    assert (analytics["volatility_pct"], analytics["sharpe_ratio"], analytics["max_drawdown_pct"]) == (None, None, None)


def test_recording_a_snapshot(client: TestClient, provider: FakeProvider, portfolio: dict[str, Any], tmp_path: Path) -> None:
    pid = portfolio["id"]
    submit(client, pid, quantity="4")
    reprice(provider, tmp_path, [make_bar(YESTERDAY, 110.0)])
    res = client.post(f"{URL}/{pid}/snapshots")
    assert res.status_code == 201
    snapshot = res.json()
    assert (snapshot["cash"], snapshot["positions_value"], snapshot["equity"], snapshot["unrealized_pnl"]) == (
        "599.00", "440.00", "1039.00", "39.00",
    )
    assert snapshot["prices_as_of"] == YESTERDAY
    history = client.get(f"{URL}/{pid}/equity-history").json()
    assert [s["equity"] for s in history] == ["1000.00", "1039.00"]
    analytics = client.get(f"{URL}/{pid}/analytics").json()
    assert (analytics["snapshots"], analytics["equity"], analytics["total_return_pct"]) == (2, "1039.00", "3.9000")
