from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app.contracts import EquitySnapshot
from app.portfolio.analytics import compute_metrics

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
