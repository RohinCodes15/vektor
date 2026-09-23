from datetime import date
from typing import Annotated

import pytest
from fastapi import Query
from fastapi.testclient import TestClient

from app.config import Settings
from app.market_data.errors import InvalidMarketData, MarketDataNotFound, MarketDataUnavailable
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app(Settings(environment="test"))

    @app.get("/probe/validation")
    def validation(day: Annotated[date, Query()], count: Annotated[int, Query(ge=1)] = 1) -> dict[str, str]:
        return {"day": day.isoformat()}

    @app.get("/probe/market/{kind}")
    def market(kind: str) -> None:
        errors = {"missing": MarketDataNotFound("no data"), "invalid": InvalidMarketData("bad data"),
                  "down": MarketDataUnavailable("provider down")}
        raise errors[kind]

    @app.get("/probe/crash")
    def crash() -> None:
        raise RuntimeError("secret internal detail")

    return TestClient(app, raise_server_exceptions=False)


def test_validation_errors_are_a_single_readable_detail(client: TestClient) -> None:
    res = client.get("/probe/validation", params={"day": "not-a-date", "count": 0})
    assert res.status_code == 422
    body = res.json()
    assert body.keys() == {"detail"} and isinstance(body["detail"], str)
    assert body["detail"].startswith("day: Input should be a valid date")
    assert "count: Input should be greater than or equal to 1" in body["detail"]
    assert "not-a-date" not in body["detail"]


def test_missing_parameters_are_reported(client: TestClient) -> None:
    res = client.get("/probe/validation")
    assert res.status_code == 422 and res.json() == {"detail": "day: Field required"}


@pytest.mark.parametrize(("kind", "status", "detail"), [("missing", 404, "no data"), ("invalid", 502, "bad data"), ("down", 503, "provider down")])
def test_market_data_errors_map_to_status_codes(client: TestClient, kind: str, status: int, detail: str) -> None:
    res = client.get(f"/probe/market/{kind}")
    assert res.status_code == status and res.json() == {"detail": detail}


def test_unexpected_errors_hide_internals(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    res = client.get("/probe/crash")
    assert res.status_code == 500 and res.json() == {"detail": "Internal server error"}
    assert "secret internal detail" not in res.text
    assert any(r.getMessage() == "unhandled error" and r.exc_info for r in caplog.records)


def test_unknown_routes_keep_the_error_shape(client: TestClient) -> None:
    res = client.get("/api/v1/nope")
    assert res.status_code == 404 and res.json() == {"detail": "Not Found"}
