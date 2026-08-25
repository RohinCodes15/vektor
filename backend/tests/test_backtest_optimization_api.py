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

URL = "/api/v1/backtests/optimizations"
FIRST_DAY = date(2024, 1, 2)
# 40 daily closes with swings, so short SMA and RSI settings trade in both segments.
CLOSES = [10, 11, 12, 11, 10, 9, 10, 12, 13, 12, 11, 10, 11, 12, 14, 13, 12, 11, 12, 13,
          15, 14, 13, 12, 11, 12, 14, 15, 16, 15, 14, 13, 12, 13, 14, 16, 17, 16, 15, 14]
TRAIN_BARS = 28  # 40 * 70 // 100
GRID: dict[str, Any] = {"kind": "sma_crossover", "fast_windows": [2, 3], "slow_windows": [4, 5, 6]}
BODY: dict[str, Any] = {
    "symbol": "aapl", "start": "2024-01-01", "end": "2024-06-28", "starting_cash": "1000",
    "grid": GRID, "objective": "total_return_pct", "fee_per_trade": "1", "slippage_bps": "10",
}


def bars(closes: list[float]) -> list[PriceBar]:
    return [
        PriceBar(date=FIRST_DAY + timedelta(days=i), open=c, high=c + 1, low=c - 1, close=c, adjusted_close=c,
                 volume=1000)
        for i, c in enumerate(closes)
    ]


def make_client(provider: FakeProvider, tmp_path: Path) -> TestClient:
    settings = Settings(
        environment="test",
        market_data_cache_path=tmp_path / "cache.sqlite3",
        portfolio_db_path=tmp_path / "portfolios.sqlite3",
        backtest_db_path=tmp_path / "backtests.sqlite3",
    )
    return TestClient(create_app(settings, market_data_provider=provider))


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return make_client(FakeProvider(bars(CLOSES)), tmp_path)


def test_optimization_splits_chronologically_and_ranks_on_training_data(client: TestClient) -> None:
    res = client.post(URL, json=BODY)
    assert res.status_code == 200
    body = res.json()
    split = body["split"]
    assert (body["mode"], body["bars"], split["train_bars"], split["test_bars"]) == ("paper", 40, TRAIN_BARS, 12)
    assert split["train_last_date"] < split["test_first_date"]
    assert (body["candidates_total"], body["candidates_evaluated"], body["candidates_skipped"]) == (6, 6, 0)
    ranked = body["ranked"]
    assert [c["rank"] for c in ranked] == [1, 2, 3, 4, 5, 6]
    values = [float(c["objective_value"]) for c in ranked]
    assert values == sorted(values, reverse=True)
    assert all(c["objective_value"] == c["train_metrics"]["total_return_pct"] for c in ranked)
    selected = body["selected"]
    assert selected["strategy"] == ranked[0]["strategy"]
    assert selected["train"]["metrics"] == ranked[0]["train_metrics"]
    assert (selected["train"]["bars"], selected["test"]["bars"]) == (TRAIN_BARS, 12)
    assert selected["test"]["equity_curve"][0]["equity"] == "1000.00"
    assert selected["test"]["first_date"] == split["test_first_date"]
    assert body["limitations"] and "not guaranteed" in body["disclaimer"]


def test_segments_equal_standalone_backtests_on_the_same_dates(client: TestClient) -> None:
    body = client.post(URL, json=BODY).json()
    selected = body["selected"]
    for segment in ("train", "test"):
        part = selected[segment]
        standalone = client.post("/api/v1/backtests", json={
            **{k: v for k, v in BODY.items() if k not in ("symbol", "grid", "objective")},
            "symbols": ["AAPL"], "strategy": selected["strategy"],
            "start": part["first_date"], "end": part["last_date"],
        }).json()
        assert part["metrics"] == standalone["metrics"]
        assert part["equity_curve"] == standalone["equity_curve"]
        assert part["warnings"] == standalone["warnings"]


def test_test_segment_prices_cannot_change_the_ranking(tmp_path: Path) -> None:
    changed = CLOSES[:TRAIN_BARS] + [c * 3 if i % 2 else c / 2 for i, c in enumerate(CLOSES[TRAIN_BARS:])]
    original = make_client(FakeProvider(bars(CLOSES)), tmp_path / "a").post(URL, json=BODY).json()
    shifted = make_client(FakeProvider(bars(changed)), tmp_path / "b").post(URL, json=BODY).json()
    assert original["ranked"] == shifted["ranked"]
    assert original["selected"]["train"] == shifted["selected"]["train"]
    assert original["selected"]["test"] != shifted["selected"]["test"]


def test_same_request_gives_the_same_body(client: TestClient) -> None:
    assert client.post(URL, json=BODY).json() == client.post(URL, json=BODY).json()


def test_top_n_limits_the_ranked_list(client: TestClient) -> None:
    body = client.post(URL, json={**BODY, "top_n": 2}).json()
    assert len(body["ranked"]) == 2 and body["candidates_evaluated"] == 6


def test_rsi_grid_with_drawdown_objective(client: TestClient) -> None:
    grid = {"kind": "rsi", "periods": [2, 3], "oversold": [30, 40], "overbought": [60, 70]}
    body = client.post(URL, json={**BODY, "grid": grid, "objective": "max_drawdown_pct"}).json()
    values = [float(c["objective_value"]) for c in body["ranked"]]
    assert values == sorted(values, reverse=True) and all(v <= 0 for v in values)
    assert body["ranked"][0]["strategy"]["kind"] == "rsi"


def test_candidates_longer_than_a_segment_are_skipped(client: TestClient) -> None:
    grid = {"kind": "sma_crossover", "fast_windows": [2], "slow_windows": [4, 11]}
    body = client.post(URL, json={**BODY, "grid": grid}).json()
    assert (body["candidates_total"], body["candidates_evaluated"], body["candidates_skipped"]) == (2, 1, 1)
    assert body["selected"]["strategy"]["slow_window"] == 4


def test_no_candidate_with_a_defined_objective_selects_nothing(tmp_path: Path) -> None:
    flat = make_client(FakeProvider(bars([10] * 40)), tmp_path)
    body = flat.post(URL, json={**BODY, "objective": "sharpe_ratio"}).json()
    assert body["ranked"] == [] and body["selected"] is None
    assert body["candidates_unranked"] == 6 and "sharpe_ratio" in body["selection_reason"]


def test_too_little_history_is_rejected_with_the_needed_days(tmp_path: Path) -> None:
    short = make_client(FakeProvider(bars(CLOSES[:15])), tmp_path)
    res = short.post(URL, json=BODY)
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert "needs 6 trading days" in detail and "10 training and 5 test days" in detail


def test_invalid_grid_is_rejected_before_fetching(tmp_path: Path) -> None:
    provider = FakeProvider(bars(CLOSES))
    res = make_client(provider, tmp_path).post(URL, json={**BODY, "grid": {**GRID, "fast_windows": [9]}})
    assert res.status_code == 422 and "no valid combination" in res.json()["detail"]
    assert provider.calls == []


def test_non_usd_and_provider_errors_are_reported(tmp_path: Path) -> None:
    euro = make_client(FakeProvider(bars(CLOSES), currency="EUR"), tmp_path / "a").post(URL, json=BODY)
    assert euro.status_code == 422 and "EUR" in euro.json()["detail"]
    down = FakeProvider(error=MarketDataUnavailable("Yahoo Finance is unreachable"))
    assert make_client(down, tmp_path / "b").post(URL, json=BODY).status_code == 503
