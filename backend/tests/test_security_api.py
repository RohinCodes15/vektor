"""Phase 4A hardening, exercised through the real app: limits, headers, CORS, docs, and safe errors."""

import logging
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


def test_api_responses_carry_security_headers_and_a_request_id(tmp_path: Path) -> None:
    res = make_client(tmp_path).get("/api/v1/health")
    assert res.status_code == 200
    assert res.headers["x-content-type-options"] == "nosniff" and res.headers["x-frame-options"] == "DENY"
    assert res.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert len(res.headers["x-request-id"]) == 32
    assert "strict-transport-security" not in res.headers


def test_production_hides_docs_and_sends_hsts(tmp_path: Path) -> None:
    client = make_client(tmp_path, environment="production", cors_origins=["https://vektor.example"])
    assert [client.get(path).status_code for path in ("/docs", "/redoc", "/openapi.json")] == [404, 404, 404]
    health = client.get("/api/v1/health")
    assert health.status_code == 200 and health.json()["environment"] == "production"
    assert health.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"


def test_development_keeps_the_interactive_docs(tmp_path: Path) -> None:
    client = make_client(tmp_path, environment="development")
    assert client.get("/docs").status_code == 200 and client.get("/openapi.json").status_code == 200


def test_cors_allows_the_configured_origin_and_exposes_limit_headers(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    preflight = client.options("/api/v1/backtests", headers={
        "origin": ORIGIN, "access-control-request-method": "POST", "access-control-request-headers": "content-type",
    })
    assert preflight.status_code == 200 and preflight.headers["access-control-allow-origin"] == ORIGIN
    assert "PUT" not in preflight.headers["access-control-allow-methods"]
    res = client.get("/api/v1/health", headers={"origin": ORIGIN})
    assert res.headers["access-control-allow-origin"] == ORIGIN
    assert set(res.headers["access-control-expose-headers"].split(", ")) == {"x-request-id", "retry-after"}


def test_cors_rejects_other_origins_and_unlisted_headers(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    assert "access-control-allow-origin" not in client.get(
        "/api/v1/health", headers={"origin": "https://evil.example"}
    ).headers
    preflight = client.options("/api/v1/backtests", headers={
        "origin": ORIGIN, "access-control-request-method": "POST", "access-control-request-headers": "x-api-key",
    })
    assert preflight.status_code == 400


def test_production_without_configured_origins_allows_no_browser_origin(tmp_path: Path) -> None:
    client = make_client(tmp_path, environment="production", cors_origins=[])  # explicitly none (Phase 5A)
    res = client.get("/api/v1/health", headers={"origin": ORIGIN})
    assert res.status_code == 200 and "access-control-allow-origin" not in res.headers


def test_an_oversize_body_is_rejected_before_any_work(tmp_path: Path) -> None:
    provider = FakeProvider(price_bars(SWING))
    client = make_client(tmp_path, provider, max_request_body_bytes=1024)
    res = client.post("/api/v1/backtests", json={**BACKTEST, "padding": "x" * 2000})
    assert res.status_code == 413 and res.json() == {"detail": "Request body is larger than the 1024-byte limit."}
    assert provider.calls == []


def test_expensive_requests_have_their_own_stricter_rate_limit(tmp_path: Path) -> None:
    client = make_client(tmp_path, expensive_rate_limit_per_minute=2, rate_limit_per_minute=100)
    assert [client.post("/api/v1/backtests", json=BACKTEST).status_code for _ in range(2)] == [201, 201]
    limited = client.post("/api/v1/backtests/comparisons", json=COMPARISON, headers={"origin": ORIGIN})
    assert limited.status_code == 429 and "Try again in" in limited.json()["detail"]
    assert int(limited.headers["retry-after"]) >= 1
    assert limited.headers["access-control-allow-origin"] == ORIGIN  # the browser can read the 429
    assert client.get("/api/v1/backtests").status_code == 200  # reading results is not an expensive request


def test_general_requests_are_rate_limited_too(tmp_path: Path) -> None:
    client = make_client(tmp_path, rate_limit_per_minute=3)
    assert [client.get("/api/v1/health").status_code for _ in range(4)] == [200, 200, 200, 429]


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


def test_unexpected_failures_never_expose_internal_details(tmp_path: Path) -> None:
    client = make_client(tmp_path, FakeProvider(error=RuntimeError("db password=hunter2 at /srv/secret.py")))
    res = client.post("/api/v1/backtests", json=BACKTEST)
    assert res.status_code == 500 and res.json() == {"detail": "Internal server error"}
    assert "hunter2" not in res.text


def test_unexpected_failures_keep_cors_security_headers_and_the_request_id(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client = make_client(tmp_path, FakeProvider(error=RuntimeError("db password=hunter2")))
    logging.getLogger().addHandler(caplog.handler)  # create_app reconfigures logging and drops pytest's handler
    res = client.post("/api/v1/backtests", json=BACKTEST, headers={"Origin": ORIGIN, "x-request-id": "trace-500"})
    assert res.status_code == 500 and res.json() == {"detail": "Internal server error"}
    # Without CORS headers a browser hides the response and the frontend sees a network error instead.
    assert res.headers["access-control-allow-origin"] == ORIGIN
    assert res.headers["x-request-id"] == "trace-500"
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["cache-control"] == "no-store"
    assert res.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    errors = [r for r in caplog.records if r.getMessage() == "unhandled error"]
    assert len(errors) == 1 and errors[0].exc_info is not None
    assert "hunter2" not in res.text


def test_validation_errors_do_not_echo_submitted_values(tmp_path: Path) -> None:
    res = make_client(tmp_path).post("/api/v1/backtests", json={**BACKTEST, "starting_cash": "sk-ant-secret-xyz"})
    assert res.status_code == 422 and "sk-ant-secret-xyz" not in res.text


def test_limit_responses_are_documented_for_expensive_endpoints(tmp_path: Path) -> None:
    paths = make_client(tmp_path).get("/openapi.json").json()["paths"]
    for path in ("/api/v1/backtests", "/api/v1/backtests/comparisons", "/api/v1/backtests/optimizations",
                 "/api/v1/backtests/{backtest_id}/analysis"):
        assert set(paths[path]["post"]["responses"]) >= {"413", "429", "503"}


OWNER_KEY = "o" * 48
OWNER = {"x-vektor-owner-key": OWNER_KEY}


def public_client(tmp_path: Path) -> TestClient:
    return make_client(tmp_path, environment="production", cors_origins=["https://vektor.example"], owner_key=OWNER_KEY)


def test_in_production_visitors_cannot_create_change_or_trade_paper_portfolios(tmp_path: Path) -> None:
    client = public_client(tmp_path)
    assert client.post("/api/v1/portfolios", json={"name": "x", "starting_cash": "100.00"}).status_code == 403
    portfolio = client.post("/api/v1/portfolios", json={"name": "Owner", "starting_cash": "1000.00"}, headers=OWNER)
    assert portfolio.status_code == 201
    pid = portfolio.json()["id"]
    order = {"client_order_id": "o1", "symbol": "AAPL", "side": "buy", "quantity": "1"}
    assert client.post(f"/api/v1/portfolios/{pid}/orders", json=order).status_code == 403
    assert client.patch(f"/api/v1/portfolios/{pid}", json={"name": "vandal"}).status_code == 403
    assert client.delete(f"/api/v1/portfolios/{pid}").status_code == 403
    assert client.post(f"/api/v1/portfolios/{pid}/snapshots").status_code == 403
    # Reading stays open, and nothing a visitor sent changed the owner's portfolio.
    listing = client.get("/api/v1/portfolios")
    assert listing.status_code == 200 and [p["name"] for p in listing.json()] == ["Owner"]
    assert client.get(f"/api/v1/portfolios/{pid}/transactions").json() == []


def test_in_production_visitors_run_research_but_cannot_list_every_stored_backtest(tmp_path: Path) -> None:
    client = public_client(tmp_path)
    backtest = client.post("/api/v1/backtests", json=BACKTEST)
    assert backtest.status_code == 201
    assert client.get(f"/api/v1/backtests/{backtest.json()['id']}").status_code == 200
    assert client.post("/api/v1/backtests/comparisons", json=COMPARISON).status_code == 200
    assert client.post("/api/v1/backtests/optimizations", json=OPTIMIZATION).status_code == 200
    assert client.get("/api/v1/backtests").status_code == 403
    assert client.get("/api/v1/backtests", headers=OWNER).status_code == 200


def test_owner_only_rejections_keep_cors_so_the_browser_can_read_them(tmp_path: Path) -> None:
    client = public_client(tmp_path)
    res = client.post("/api/v1/portfolios", json={}, headers={"origin": "https://vektor.example"})
    assert res.status_code == 403 and res.headers["access-control-allow-origin"] == "https://vektor.example"
