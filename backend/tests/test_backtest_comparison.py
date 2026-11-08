from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.backtest.comparison import differences, leaders
from app.contracts import BacktestComparisonCreate, BacktestMetrics

D = Decimal
BASE: dict[str, Any] = {
    "final_equity": "1000.00", "total_return_pct": "0", "annualized_return_pct": "0", "volatility_pct": "10",
    "max_drawdown_pct": "-5", "sharpe_ratio": "1", "win_rate_pct": None, "trades": 1, "closed_trades": 0,
    "winning_trades": 0, "total_fees": "0.00",
}


def metrics(**overrides: Any) -> BacktestMetrics:
    return BacktestMetrics.model_validate({**BASE, **overrides})


def comparison(**overrides: Any) -> BacktestComparisonCreate:
    body: dict[str, Any] = {
        "symbol": " aapl ", "start": "2024-01-01", "end": "2024-06-28", "starting_cash": "1000",
        "strategies": [{"kind": "buy_and_hold"}, {"kind": "rsi"}], **overrides,
    }
    return BacktestComparisonCreate.model_validate(body)


def test_differences_subtract_the_baseline_and_are_null_when_either_side_is_undefined() -> None:
    diff = differences(metrics(total_return_pct="12.5", win_rate_pct="50"), metrics(total_return_pct="2.25"))
    assert diff.total_return_pct == D("10.25") and diff.volatility_pct == D(0)
    assert diff.win_rate_pct is None


def test_leaders_pick_the_best_value_per_metric_with_lower_volatility_and_shallower_drawdown_better() -> None:
    result = {
        leader.metric: leader
        for leader in leaders([
            metrics(total_return_pct="5", volatility_pct="20", max_drawdown_pct="-10"),
            metrics(total_return_pct="8", volatility_pct="12", max_drawdown_pct="-3"),
        ])
    }
    assert result["total_return_pct"].leaders == [1] and result["total_return_pct"].better == "higher"
    assert result["volatility_pct"].leaders == [1] and result["volatility_pct"].better == "lower"
    assert result["max_drawdown_pct"].leaders == [1]


def test_leaders_share_ties_and_skip_unavailable_strategies_and_null_metrics() -> None:
    result = {
        leader.metric: leader
        for leader in leaders([metrics(total_return_pct="8"), None, metrics(total_return_pct="8"), metrics()])
    }
    assert result["total_return_pct"].leaders == [0, 2] and result["total_return_pct"].reason is None


def test_no_leader_when_fewer_than_two_strategies_have_the_metric_or_all_are_equal() -> None:
    result = {leader.metric: leader for leader in leaders([metrics(win_rate_pct="60"), metrics(), None])}
    assert result["win_rate_pct"].leaders == []
    assert result["win_rate_pct"].reason == "Fewer than 2 strategies have this metric."
    assert result["sharpe_ratio"].leaders == [] and result["sharpe_ratio"].reason == "Every compared strategy is equal."


def test_request_normalizes_the_symbol_and_shares_backtest_settings() -> None:
    request = comparison(fee_per_trade="1", slippage_bps="5.0")
    assert request.symbol == "AAPL" and request.fee_per_trade == D("1.00") and request.slippage_bps == D(5)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"strategies": [{"kind": "buy_and_hold"}]}, "at least 2"),
        ({"strategies": [{"kind": "rsi", "period": p} for p in range(2, 8)]}, "at most 5"),
        ({"strategies": [{"kind": "rsi"}, {"kind": "rsi", "period": 14, "oversold": "30.00"}]}, "must not repeat"),
        ({"symbol": "^GSPC"}, "ticker"),
        ({"start": "2024-07-01"}, "start must be before end"),
        ({"symbols": ["AAPL"]}, "Extra inputs"),
    ],
)
def test_invalid_requests_are_rejected(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        comparison(**overrides)
