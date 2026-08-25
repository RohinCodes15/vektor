from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.contracts import (
    MAX_OPTIMIZATION_CANDIDATES,
    BacktestOptimizationCreate,
    RsiGrid,
    RsiStrategy,
    SmaCrossoverGrid,
    SmaCrossoverStrategy,
)

BASE: dict[str, Any] = {
    "symbol": "aapl", "start": "2024-01-01", "end": "2024-06-28", "starting_cash": "1000",
    "grid": {"kind": "sma_crossover", "fast_windows": [2, 3], "slow_windows": [5, 8]},
    "objective": "sharpe_ratio",
}


def request(**changes: Any) -> BacktestOptimizationCreate:
    return BacktestOptimizationCreate.model_validate({**BASE, **changes})


def test_defaults_and_symbol_normalization() -> None:
    body = request()
    assert (body.symbol, body.train_pct, body.top_n) == ("AAPL", 70, 10)


def test_sma_grid_expands_valid_pairs_in_ascending_order() -> None:
    grid = SmaCrossoverGrid(kind="sma_crossover", fast_windows=[10, 5], slow_windows=[8, 20])
    assert grid.fast_windows == [5, 10]
    assert grid.strategies() == [
        SmaCrossoverStrategy(kind="sma_crossover", fast_window=5, slow_window=8),
        SmaCrossoverStrategy(kind="sma_crossover", fast_window=5, slow_window=20),
        SmaCrossoverStrategy(kind="sma_crossover", fast_window=10, slow_window=20),
    ]


def test_rsi_grid_skips_crossed_thresholds_and_canonicalizes_levels() -> None:
    grid = RsiGrid(kind="rsi", periods=[14], oversold=[Decimal("30.0"), 50], overbought=[40, 70])
    assert grid.oversold == [Decimal(30), Decimal(50)]
    assert [(s.oversold, s.overbought) for s in grid.strategies()] == [(30, 40), (30, 70), (50, 70)]
    assert all(isinstance(s, RsiStrategy) for s in grid.strategies())


@pytest.mark.parametrize(
    "grid",
    [
        {"kind": "sma_crossover", "fast_windows": [2, 2], "slow_windows": [5]},
        {"kind": "sma_crossover", "fast_windows": [1], "slow_windows": [5]},
        {"kind": "sma_crossover", "fast_windows": [2], "slow_windows": [501]},
        {"kind": "sma_crossover", "fast_windows": [], "slow_windows": [5]},
        {"kind": "sma_crossover", "fast_windows": list(range(2, 23)), "slow_windows": [100]},
        {"kind": "rsi", "periods": [1], "oversold": [30], "overbought": [70]},
        {"kind": "rsi", "periods": [14], "oversold": [0], "overbought": [70]},
        {"kind": "rsi", "periods": [14], "oversold": [30], "overbought": [100]},
        {"kind": "rsi", "periods": [14], "oversold": [30.123], "overbought": [70]},
        {"kind": "buy_and_hold"},
    ],
)
def test_invalid_grid_values_are_rejected(grid: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        request(grid=grid)


def test_grid_without_a_valid_combination_is_rejected() -> None:
    with pytest.raises(ValidationError, match="no valid combination"):
        request(grid={"kind": "sma_crossover", "fast_windows": [10], "slow_windows": [5, 10]})


def test_workload_limit_counts_valid_combinations_only() -> None:
    at_limit = {"kind": "sma_crossover", "fast_windows": list(range(2, 12)), "slow_windows": list(range(20, 30))}
    assert len(request(grid=at_limit).grid.strategies()) == MAX_OPTIMIZATION_CANDIDATES
    over = {"kind": "rsi", "periods": [2, 3, 4, 5, 6], "oversold": [10, 20, 30, 40, 45], "overbought": [50, 60, 70, 80, 90]}
    with pytest.raises(ValidationError, match="at most 100"):
        request(grid=over)


@pytest.mark.parametrize(
    "changes",
    [
        {"objective": "win_rate_pct"},
        {"train_pct": 49},
        {"train_pct": 91},
        {"top_n": 0},
        {"top_n": 101},
        {"symbol": "^GSPC"},
        {"start": "2024-06-28", "end": "2024-01-01"},
        {"unexpected": 1},
    ],
)
def test_invalid_settings_are_rejected(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        request(**changes)
