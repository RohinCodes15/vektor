from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.backtest.optimization import Scored, overfitting_report, rank, split_calendar
from app.contracts import BacktestMetrics, RsiGrid, RsiStrategy, SmaCrossoverGrid, SmaCrossoverStrategy

SMA_GRID = SmaCrossoverGrid(kind="sma_crossover", fast_windows=[2, 3, 4], slow_windows=[10, 15, 20])


def metrics(**changes: Any) -> BacktestMetrics:
    base: dict[str, Any] = {
        "final_equity": Decimal("1000.00"), "total_return_pct": Decimal(0), "annualized_return_pct": Decimal(0),
        "volatility_pct": Decimal(10), "max_drawdown_pct": Decimal(-5), "sharpe_ratio": Decimal(1),
        "win_rate_pct": Decimal(50), "trades": 20, "closed_trades": 10, "winning_trades": 5,
        "total_fees": Decimal("0.00"),
    }
    counts = ("trades", "closed_trades", "winning_trades")
    decimals = {k: v if v is None or k in counts else Decimal(str(v)) for k, v in changes.items()}
    return BacktestMetrics(**{**base, **decimals})


def sma(fast: int, slow: int) -> SmaCrossoverStrategy:
    return SmaCrossoverStrategy(kind="sma_crossover", fast_window=fast, slow_window=slow)


def scored(index: int, **changes: Any) -> Scored:
    return Scored(index, sma(2 + index, 50), metrics(**changes))


def test_split_is_chronological_and_disjoint() -> None:
    calendar = [date(2024, 1, 1) + timedelta(days=i) for i in range(11)]
    split = split_calendar(calendar, 70)
    assert (len(split.train), len(split.test)) == (7, 4)
    assert split.train + split.test == tuple(calendar)
    assert max(split.train) < min(split.test)


def test_split_rounds_the_training_share_down() -> None:
    calendar = [date(2024, 1, 1) + timedelta(days=i) for i in range(3)]
    assert len(split_calendar(calendar, 50).train) == 1


def test_higher_total_return_and_sharpe_rank_first() -> None:
    candidates = [scored(0, total_return_pct=5, sharpe_ratio=0.5), scored(1, total_return_pct=9, sharpe_ratio=0.2)]
    assert [s.index for s in rank(candidates, "total_return_pct")] == [1, 0]
    assert [s.index for s in rank(candidates, "sharpe_ratio")] == [0, 1]


def test_shallowest_drawdown_ranks_first() -> None:
    candidates = [scored(0, max_drawdown_pct=-20), scored(1, max_drawdown_pct=-3), scored(2, max_drawdown_pct=-8)]
    assert [s.index for s in rank(candidates, "max_drawdown_pct")] == [1, 2, 0]


def test_undefined_objective_is_left_unranked() -> None:
    candidates = [scored(0, sharpe_ratio=None), scored(1, sharpe_ratio=-1)]
    assert [s.index for s in rank(candidates, "sharpe_ratio")] == [1]
    assert rank([scored(0, sharpe_ratio=None)], "sharpe_ratio") == []


def test_ties_break_on_total_return_then_grid_order() -> None:
    candidates = [
        scored(0, sharpe_ratio=1, total_return_pct=2),
        scored(1, sharpe_ratio=1, total_return_pct=4),
        scored(2, sharpe_ratio=1, total_return_pct=2),
    ]
    assert [s.index for s in rank(candidates, "sharpe_ratio")] == [1, 0, 2]
    assert [s.index for s in rank(list(reversed(candidates)), "sharpe_ratio")] == [1, 0, 2]


def test_report_gaps_are_test_minus_train_and_null_when_undefined() -> None:
    train = metrics(annualized_return_pct=30, sharpe_ratio=2, max_drawdown_pct=-4)
    test = metrics(annualized_return_pct=10, sharpe_ratio=None, max_drawdown_pct=-9)
    report = overfitting_report(sma(3, 15), SMA_GRID, 6, train, test)
    assert report.annualized_return_gap_pct == Decimal(-20)
    assert report.sharpe_gap is None
    assert report.max_drawdown_gap_pct == Decimal(-5)


def test_reversal_and_sharpe_decay_are_flagged() -> None:
    train = metrics(total_return_pct=12, sharpe_ratio=2)
    test = metrics(total_return_pct=-1, sharpe_ratio=0.9)
    codes = [f.code for f in overfitting_report(sma(3, 15), SMA_GRID, 6, train, test).flags]
    assert codes == ["return_reversal", "sharpe_decay"]


def test_consistent_results_inside_the_grid_raise_no_flag() -> None:
    train = metrics(total_return_pct=12, sharpe_ratio=2)
    test = metrics(total_return_pct=5, sharpe_ratio=1.5)
    assert overfitting_report(sma(3, 15), SMA_GRID, 6, train, test).flags == []


def test_few_trades_edge_of_grid_and_many_candidates_are_flagged() -> None:
    train = metrics(closed_trades=2, winning_trades=1)
    report = overfitting_report(sma(4, 20), SMA_GRID, 51, train, metrics())
    codes = [f.code for f in report.flags]
    assert codes == ["few_trades", "edge_of_grid", "many_candidates"]
    assert "fast_window, slow_window" in report.flags[1].message


def test_single_value_dimensions_are_never_at_an_edge() -> None:
    grid = RsiGrid(kind="rsi", periods=[14], oversold=[20, 30, 40], overbought=[70])
    strategy = RsiStrategy(kind="rsi", period=14, oversold=Decimal(30), overbought=Decimal(70))
    assert overfitting_report(strategy, grid, 3, metrics(), metrics()).flags == []
