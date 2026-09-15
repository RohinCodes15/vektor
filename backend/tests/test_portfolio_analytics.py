from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app.contracts import EquitySnapshot
from app.portfolio.analytics import compute_metrics, daily_returns, daily_series

D = Decimal
PORTFOLIO = uuid4()
DAY_ONE = datetime(2024, 1, 8, 21, 0, tzinfo=UTC)


def snap(day: int, equity: str, deposits: str = "1000.00", hour: int = 21) -> EquitySnapshot:
    return EquitySnapshot(
        id=uuid4(), portfolio_id=PORTFOLIO, taken_at=DAY_ONE.replace(hour=hour) + timedelta(days=day),
        cash=D(equity), positions_value=D("0.00"), equity=D(equity), net_deposits=D(deposits),
        realized_pnl=D("0.00"), unrealized_pnl=D("0.00"), prices_as_of=None,
    )


def test_no_snapshots_has_no_metrics() -> None:
    metrics = compute_metrics([])
    assert metrics.daily_observations == 0
    assert (metrics.total_return_pct, metrics.latest_daily_return_pct, metrics.volatility_pct,
            metrics.max_drawdown_pct, metrics.sharpe_ratio) == (None, None, None, None, None)


def test_one_snapshot_only_has_total_return() -> None:
    metrics = compute_metrics([snap(0, "1050.00")])
    assert metrics.total_return_pct == D("5.0000")
    assert (metrics.latest_daily_return_pct, metrics.volatility_pct, metrics.max_drawdown_pct, metrics.sharpe_ratio) == (
        None, None, None, None,
    )


def test_two_days_give_a_daily_return_and_drawdown_but_no_volatility() -> None:
    metrics = compute_metrics([snap(0, "1000.00"), snap(1, "950.00")])
    assert metrics.latest_daily_return_pct == D("-5.0000")
    assert metrics.max_drawdown_pct == D("-5.0000")
    assert metrics.volatility_pct is None and metrics.sharpe_ratio is None


def test_full_metrics_match_an_independent_calculation() -> None:
    metrics = compute_metrics([snap(0, "1000.00"), snap(1, "1100.00"), snap(2, "990.00"), snap(3, "1089.00")])
    # Daily returns +10%, -10%, +10% (statistics.stdev * sqrt(252) = 183.303%, Sharpe 4.5826).
    assert metrics.daily_observations == 4
    assert metrics.total_return_pct == D("8.9000")
    assert metrics.latest_daily_return_pct == D("10.0000")
    assert metrics.volatility_pct == D("183.3030")
    assert metrics.sharpe_ratio == D("4.5826")
    assert metrics.max_drawdown_pct == D("-10.0000")  # 1.10 peak to 0.99


def test_zero_volatility_has_no_sharpe_ratio() -> None:
    metrics = compute_metrics([snap(0, "1000.00"), snap(1, "1000.00"), snap(2, "1000.00")])
    assert metrics.volatility_pct == D("0.0000")
    assert metrics.sharpe_ratio is None
    assert metrics.max_drawdown_pct == D("0.0000")
    assert metrics.total_return_pct == D("0.0000")


def test_deposits_are_not_counted_as_returns() -> None:
    series = [snap(0, "1000.00", "1000.00"), snap(1, "1600.00", "1500.00"), snap(2, "1680.00", "1500.00")]
    # Day 2: (1600 - 500 deposited) / 1000 - 1 = +10%. Day 3: 1680 / 1600 - 1 = +5%.
    assert daily_returns(series) == [D("0.1"), D("0.05")]
    metrics = compute_metrics(series)
    assert metrics.total_return_pct == D("12.0000")  # 1680 / 1500 deposited - 1
    assert metrics.volatility_pct == D("56.1249")
    assert metrics.sharpe_ratio == D("33.6749")
    assert metrics.max_drawdown_pct == D("0.0000")


def test_the_last_snapshot_of_each_day_is_used() -> None:
    snapshots = [snap(0, "1000.00", hour=14), snap(0, "1010.00", hour=20), snap(1, "1111.00", hour=15)]
    series = daily_series(snapshots)
    assert [s.equity for s in series] == [D("1010.00"), D("1111.00")]
    metrics = compute_metrics(snapshots)
    assert metrics.daily_observations == 2
    assert metrics.latest_daily_return_pct == D("10.0000")


def test_days_without_snapshots_are_not_filled() -> None:
    series = daily_series([snap(0, "1000.00"), snap(5, "1100.00")])
    assert len(series) == 2
    assert daily_returns(series) == [D("0.1")]


def test_a_return_after_zero_equity_is_undefined_and_skipped() -> None:
    snapshots = [snap(0, "0.00", "1000.00"), snap(1, "10.00", "1000.00")]
    assert daily_returns(snapshots) == [None]
    metrics = compute_metrics(snapshots)
    assert metrics.latest_daily_return_pct is None and metrics.max_drawdown_pct is None
    assert metrics.total_return_pct == D("-99.0000")


def test_a_total_loss_is_a_full_drawdown() -> None:
    metrics = compute_metrics([snap(0, "1000.00"), snap(1, "1200.00"), snap(2, "0.00")])
    assert metrics.max_drawdown_pct == D("-100.0000")
    assert metrics.total_return_pct == D("-100.0000")
