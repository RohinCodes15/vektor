from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.analysis.errors import AnalysisUnavailable, InvalidAnalysis
from app.config import Settings
from app.main import create_app
from tests.analysis_support import SWING, FakeAI, interpretation, price_bars
from tests.fakes import FakeProvider

BACKTEST = {
    "symbols": ["AAPL"], "start": "2024-01-01", "end": "2024-06-28", "starting_cash": "10000",
    "strategy": {"kind": "sma_crossover", "fast_window": 2, "slow_window": 3},
}


def client_for(tmp_path: Path, ai: FakeAI | None) -> TestClient:
    settings = Settings(
        environment="test",
        market_data_cache_path=tmp_path / "cache.sqlite3",
        portfolio_db_path=tmp_path / "portfolios.sqlite3",
        backtest_db_path=tmp_path / "backtests.sqlite3",
        ai_provider="none",  # never reach a real provider, whatever the developer's environment says
    )
    app = create_app(settings, market_data_provider=FakeProvider(price_bars(SWING)), analysis_provider=ai)
    return TestClient(app)


def analyze(client: TestClient) -> Any:
    backtest = client.post("/api/v1/backtests", json=BACKTEST).json()
    return backtest, client.post(f"/api/v1/backtests/{backtest['id']}/analysis")


def test_without_a_provider_the_endpoint_reports_unavailable_with_facts(tmp_path: Path) -> None:
    backtest, res = analyze(client_for(tmp_path, None))
    assert res.status_code == 200
    body = res.json()
    assert body.keys() == {
        "backtest_id", "mode", "status", "unavailable_reason", "generated_at", "provider", "model", "facts",
        "interpretation", "disclaimer",
    }
    assert (body["backtest_id"], body["mode"], body["status"]) == (backtest["id"], "paper", "unavailable")
    assert body["interpretation"] is None and body["provider"] is None
    facts = {fact["id"]: fact["value"] for fact in body["facts"]}
    assert facts["total_return_pct"] == f"{backtest['metrics']['total_return_pct']}%"
    assert "not investment advice" in body["disclaimer"]


def test_a_configured_provider_returns_a_grounded_interpretation(tmp_path: Path) -> None:
    ai = FakeAI()
    _, res = analyze(client_for(tmp_path, ai))
    assert res.status_code == 200
    body = res.json()
    assert (body["status"], body["provider"], body["model"]) == ("available", "anthropic", "test-model")
    assert body["interpretation"] == interpretation().model_dump(mode="json")
    assert len(ai.calls) == 1


def test_unknown_and_invalid_backtest_ids(tmp_path: Path) -> None:
    client = client_for(tmp_path, FakeAI())
    missing = client.post(f"/api/v1/backtests/{uuid4()}/analysis")
    assert missing.status_code == 404 and set(missing.json()) == {"detail"}
    assert client.post("/api/v1/backtests/not-a-uuid/analysis").status_code == 422


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (AnalysisUnavailable("The AI provider timed out. Try again later."), 503),
        (InvalidAnalysis("The AI provider returned a malformed analysis."), 502),
    ],
)
def test_provider_failures_map_to_gateway_errors(tmp_path: Path, error: Exception, status: int) -> None:
    _, res = analyze(client_for(tmp_path, FakeAI(error)))
    assert res.status_code == status
    assert res.json() == {"detail": str(error)}


def test_ungrounded_ai_output_is_a_bad_gateway(tmp_path: Path) -> None:
    _, res = analyze(client_for(tmp_path, FakeAI(interpretation(evidence=["made_up"]))))
    assert res.status_code == 502 and "not measured" in res.json()["detail"]
