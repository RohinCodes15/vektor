from decimal import Decimal

import pytest

from app.backtest.metrics import compute_performance

D = Decimal
CASH = D("1000.00")


def equity(*values: str) -> list[Decimal]:
    return [D(v) for v in values]


def test_metrics_match_an_independent_calculation() -> None:
    result = compute_performance(CASH, equity("1000", "1100", "990", "1089"), [])
    # Daily returns +10%, -10%, +10%: statistics.stdev * sqrt(252) = 183.303%, Sharpe 4.5826.
    assert result.total_return_pct == D("8.9000")
    assert result.volatility_pct == D("183.3030")
    assert result.sharpe_ratio == D("4.5826")
    assert result.max_drawdown_pct == D("-10.0000")
    assert result.drawdowns_pct == (D("0.0000"), D("0.0000"), D("-10.0000"), D("-1.0000"))
    assert float(result.annualized_return_pct) == pytest.approx((1.089 ** (252 / 3) - 1) * 100, rel=1e-9)  # type: ignore[arg-type]


def test_win_rate_counts_positive_realized_pnl_only() -> None:
    result = compute_performance(CASH, equity("1000", "1010", "1005"), [D("10"), D("-5"), D("0")])
    assert (result.closed_trades, result.winning_trades, result.win_rate_pct) == (3, 1, D("33.3333"))
    assert result.warnings == ()


def test_an_untouched_account_has_no_sharpe_ratio_or_win_rate() -> None:
    result = compute_performance(CASH, equity("1000", "1000", "1000"), [])
    assert (result.total_return_pct, result.annualized_return_pct, result.volatility_pct) == (
        D("0.0000"), D("0.0000"), D("0.0000"),
    )
    assert (result.max_drawdown_pct, result.sharpe_ratio, result.win_rate_pct) == (D("0.0000"), None, None)
    assert result.warnings == (
        "Sharpe ratio is undefined: daily returns have zero volatility.",
        "Win rate is undefined: no trade was closed.",
    )


def test_one_daily_return_has_no_volatility_or_sharpe_ratio() -> None:
    result = compute_performance(CASH, equity("1000", "1050"), [D("50")])
    assert (result.total_return_pct, result.volatility_pct, result.sharpe_ratio) == (D("5.0000"), None, None)
    assert result.annualized_return_pct is not None
    assert result.warnings == ("Volatility and Sharpe ratio need at least 2 daily returns.",)


def test_a_single_bar_has_no_annualized_return() -> None:
    result = compute_performance(CASH, equity("1000"), [])
    assert (result.annualized_return_pct, result.max_drawdown_pct) == (None, D("0.0000"))
    assert result.warnings[0] == "Annualized return needs at least 1 daily return."


def test_a_worthless_account_annualizes_to_minus_100() -> None:
    result = compute_performance(CASH, equity("1000", "500", "0"), [])
    assert (result.total_return_pct, result.annualized_return_pct, result.max_drawdown_pct) == (
        D("-100.0000"), D("-100.0000"), D("-100.0000"),
    )
