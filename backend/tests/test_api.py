import json
import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.contracts import PaperOrder, SimulationCreate
from app.logging_config import JsonFormatter
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings(environment="test", cors_origins=["http://localhost:5173"])))


def test_health_returns_ok_and_paper_mode(client: TestClient) -> None:
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["environment"] == "test"
    assert body["trading_mode"] == "paper"


def test_cors_allows_configured_origin_only(client: TestClient) -> None:
    ok = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    bad = client.get("/api/v1/health", headers={"Origin": "http://evil.example"})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in bad.headers


def test_live_trading_mode_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(trading_mode="live")


def test_unknown_dotenv_keys_are_rejected(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("VEKTOR_BROKER_API_KEY=x\n")
    with pytest.raises(ValidationError):
        Settings(_env_file=env_file)


def test_json_formatter_includes_extra_fields() -> None:
    record = logging.makeLogRecord({"msg": "hi", "levelname": "INFO", "name": "t", "trading_mode": "paper"})
    out = json.loads(JsonFormatter().format(record))
    assert out["msg"] == "hi" and out["trading_mode"] == "paper"


def test_contracts_validate_input() -> None:
    with pytest.raises(ValidationError):
        PaperOrder(symbol="AAPL", side="buy", quantity=0)
    with pytest.raises(ValidationError):
        SimulationCreate(symbols=[], starting_cash=1000, start="2025-01-01T00:00:00Z", end="2025-02-01T00:00:00Z", strategy="x")
