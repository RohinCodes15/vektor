from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from app.analysis.facts import measured_facts
from app.contracts import Backtest
from tests.analysis_support import NO_COSTS, SWING, run_backtest

D = Decimal
SMA = {"kind": "sma_crossover", "fast_window": 2, "slow_window": 3}


def by_id(backtest: Backtest) -> dict[str, str]:
    return {fact.id: fact.value for fact in measured_facts(backtest)}


def test_facts_copy_the_stored_strategy_and_metrics(tmp_path: Path) -> None:
    _, backtest = run_backtest(tmp_path, SWING, SMA)
    facts = by_id(backtest)
    metrics = backtest.metrics
    assert facts["strategy"] == (
        "SMA crossover: buy when the 2-day average crosses above the 3-day average, sell when it crosses below"
    )
    assert facts["symbols"] == "AAPL"
    assert facts["period"] == f"{backtest.first_date} to {backtest.last_date} (15 trading days)"
    assert facts["costs"] == "$1.00 per fill + 5 bps fee; 10 bps slippage"
    assert facts["total_return_pct"] == f"{metrics.total_return_pct}%"
    assert facts["max_drawdown_pct"] == f"{metrics.max_drawdown_pct}%"
    assert facts["sharpe_ratio"] == str(metrics.sharpe_ratio)
    assert (facts["fills"], facts["closed_trades"]) == (str(metrics.trades), str(metrics.closed_trades))
    assert facts["fees_pct_of_starting_cash"] == f"{(metrics.total_fees / 100).quantize(D('0.0001'))}%"


def test_trade_and_curve_facts_match_an_independent_calculation(tmp_path: Path) -> None:
    _, backtest = run_backtest(tmp_path, SWING, SMA)
    facts = by_id(backtest)
    sells = [t for t in backtest.trades if t.side == "sell"]
    buys = [t for t in backtest.trades if t.side == "buy"]
    assert sells, "the swing series must close at least one trade"
    costs = [buy.notional + buy.fee for buy in buys]
    returns = [t.realized_pnl / costs[i] * 100 for i, t in enumerate(sells)]  # type: ignore[operator]
    assert facts["best_trade_return_pct"] == f"{max(returns).quantize(D('0.0001'))}%"
    assert facts["worst_trade_return_pct"] == f"{min(returns).quantize(D('0.0001'))}%"
    days = [(t.fill_date - buys[i].fill_date).days for i, t in enumerate(sells)]
    assert facts["average_holding_days"] == f"{D(sum(days)) / len(days):.1f} calendar days"
    invested = sum(1 for p in backtest.equity_curve if p.positions_value > 0)
    assert facts["time_in_market_pct"] == f"{(D(invested) / backtest.bars * 100).quantize(D('0.0001'))}%"


def test_facts_never_include_account_dollar_amounts(tmp_path: Path) -> None:
    _, backtest = run_backtest(tmp_path, SWING, SMA)
    values = " ".join(fact.value for fact in measured_facts(backtest))
    amounts = [backtest.metrics.final_equity, backtest.config.starting_cash, *(p.equity for p in backtest.equity_curve)]
    for amount in amounts:
        assert str(amount) not in values


def test_a_rising_buy_and_hold_has_no_drawdown_and_no_closed_trades(tmp_path: Path) -> None:
    _, backtest = run_backtest(tmp_path, [10, 11, 12, 13], {"kind": "buy_and_hold"}, NO_COSTS)
    facts = by_id(backtest)
    assert facts["strategy"] == "Buy and hold: buy every symbol on the first bar and hold to the end"
    assert (facts["max_drawdown_period"], facts["longest_drawdown_days"]) == ("no drawdown", "0 trading days")
    assert facts["win_rate_pct"] == facts["average_trade_return_pct"] == facts["average_holding_days"] == "unavailable"
    assert facts["open_positions"] == "1"


def test_the_drawdown_period_names_its_peak_trough_and_recovery(tmp_path: Path) -> None:
    _, backtest = run_backtest(tmp_path, [10, 12, 11, 9, 13, 8], {"kind": "buy_and_hold"})
    facts = by_id(backtest)
    first = backtest.first_date
    # The highest close (13, day 4) comes just before the deepest fall (8, day 5), which never recovers.
    assert facts["max_drawdown_period"] == (
        f"peak {first + timedelta(days=4)}, trough {first + timedelta(days=5)}, not recovered by the last day"
    )
    _, recovered = run_backtest(tmp_path / "r", [10, 12, 9, 13], {"kind": "buy_and_hold"})
    assert by_id(recovered)["max_drawdown_period"] == (
        # Fees and slippage put day 1 below the starting cash, so the peak is the first close.
        f"peak {first}, trough {first + timedelta(days=2)}, recovered {first + timedelta(days=3)}"
    )
    # Days 1-3 sit below the starting cash (costs, then 11 and 9); day 4 sets a new peak; day 5 falls again.
    assert by_id(backtest)["longest_drawdown_days"] == "3 trading days"


def test_rsi_parameters_are_described(tmp_path: Path) -> None:
    _, backtest = run_backtest(tmp_path, SWING, {"kind": "rsi", "period": 3, "oversold": "25", "overbought": "75.5"})
    assert by_id(backtest)["strategy"] == "RSI (period 3): buy while RSI < 25, sell while RSI > 75.5"
