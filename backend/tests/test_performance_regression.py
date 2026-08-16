"""Phase 4B regression guards: optimizations must not change a single financial number.

The digests below were recorded with the code as it was before Phase 4B (commit f1eee44), on seeded synthetic
prices. Any change to a price, fill, fee, metric, curve point, ranking, or warning changes a digest.
"""

import hashlib
import random
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.backtest.service import BacktestService
from app.backtest.store import BacktestStore
from app.contracts import BacktestComparisonCreate, BacktestCreate, BacktestOptimizationCreate, PriceBar
from app.market_data.cache import HistoryCache
from app.market_data.service import MarketDataService
from tests.fakes import FakeProvider

NOW = datetime(2025, 1, 15, 12, 0, tzinfo=UTC)
COSTS = {"starting_cash": "25000.00", "fee_per_trade": "1.00", "fee_bps": "5", "slippage_bps": "10"}
SPAN = {"start": "2019-01-02", "end": "2024-12-31"}
# Excluded from the digest: they differ per run by design.
VOLATILE = {"id", "created_at"}


def seeded_bars(symbol: str) -> list[PriceBar]:
    """Six years of weekday bars from a seeded random walk; adjusted closes drift like dividends."""
    rng = random.Random(symbol)
    price, factor, day, bars = 40.0, 0.85, date(2019, 1, 2), []
    while day <= date(2024, 12, 31):
        if day.weekday() < 5:
            open_ = price
            price = max(1.0, price * (1 + rng.gauss(0.0002, 0.018)))
            high = max(open_, price) * (1 + abs(rng.gauss(0, 0.004)))
            low = min(open_, price) * (1 - abs(rng.gauss(0, 0.004)))
            factor = min(1.0, factor + 0.00005)
            bars.append(PriceBar(date=day, open=round(open_, 4), high=round(high, 4), low=round(low, 4),
                                 close=round(price, 4), adjusted_close=round(price * factor, 4), volume=1_000_000))
        day += timedelta(days=1)
    return bars


@pytest.fixture
def service(tmp_path: Path) -> BacktestService:
    provider = FakeProvider(bars_by_symbol={s: seeded_bars(s) for s in ("AAA", "BBB", "CCC")})
    cache = HistoryCache(tmp_path / "cache.sqlite3")
    market = MarketDataService(provider, cache, timedelta(hours=24), clock=lambda: NOW)
    return BacktestService(BacktestStore(tmp_path / "backtests.sqlite3"), market, clock=lambda: NOW)


def digest(model: Any) -> str:
    def strip(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: strip(v) for k, v in sorted(value.items()) if k not in VOLATILE}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    return hashlib.sha256(repr(strip(model.model_dump(mode="json"))).encode()).hexdigest()[:16]


def test_multi_symbol_backtest_matches_the_pre_optimization_result(service: BacktestService) -> None:
    result = service.run(BacktestCreate.model_validate({
        **COSTS, **SPAN, "symbols": ["AAA", "BBB", "CCC"], "position_size_pct": "90",
        "strategy": {"kind": "sma_crossover", "fast_window": 10, "slow_window": 40},
    }))
    assert digest(result) == "208fb5d32b594092"


def test_comparison_matches_the_pre_optimization_result(service: BacktestService) -> None:
    result = service.compare(BacktestComparisonCreate.model_validate({
        **COSTS, **SPAN, "symbol": "BBB", "strategies": [
            {"kind": "buy_and_hold"},
            {"kind": "sma_crossover", "fast_window": 20, "slow_window": 50},
            {"kind": "rsi", "period": 14, "oversold": 30, "overbought": 70},
            {"kind": "rsi", "period": 14, "oversold": 25, "overbought": 75},
        ],
    }))
    assert digest(result) == "80134ed6dc7c232a"


@pytest.mark.parametrize(
    ("grid", "objective", "expected"),
    [
        ({"kind": "sma_crossover", "fast_windows": [5, 10, 20, 30], "slow_windows": [40, 60, 100, 150, 200]},
         "sharpe_ratio", "22aa3b901cdbc988"),
        ({"kind": "rsi", "periods": [7, 14], "oversold": [20, 30, 40], "overbought": [60, 70, 80]},
         "max_drawdown_pct", "4c6b360e0b6211fe"),
    ],
)
def test_optimization_matches_the_pre_optimization_result(
    service: BacktestService, grid: dict[str, Any], objective: str, expected: str
) -> None:
    result = service.optimize(BacktestOptimizationCreate.model_validate({
        **COSTS, **SPAN, "symbol": "CCC", "grid": grid, "objective": objective, "top_n": 100,
    }))
    assert digest(result) == expected


def test_repeated_runs_are_deterministic(service: BacktestService) -> None:
    request = BacktestOptimizationCreate.model_validate({
        **COSTS, **SPAN, "symbol": "AAA", "objective": "total_return_pct",
        "grid": {"kind": "sma_crossover", "fast_windows": [5, 10], "slow_windows": [30, 60]},
    })
    assert digest(service.optimize(request)) == digest(service.optimize(request))
