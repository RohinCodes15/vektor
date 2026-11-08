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
