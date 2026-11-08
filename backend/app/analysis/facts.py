"""Measured facts about a stored backtest. Pure: no I/O, Decimal only. Nothing here comes from an AI provider.

Every fact is computed from the stored Backtest (also documented in backend/README.md):
- Metrics are copied from BacktestMetrics; a null metric reads "unavailable".
- Fees as a share of starting cash: total fees / starting cash * 100.
- Max drawdown period: the running equity peak before the lowest drawdown point, that trough, and the first later
  close back at or above the peak (or "not recovered").
- Longest drawdown: the most consecutive trading days with a drawdown below zero.
- Time in market: trading days ending with a position / trading days.
- Closed trade return: realized P&L / position cost, where cost = sell notional - sell fee - realized P&L, which is
  the buy notional plus the buy fee. Holding period: calendar days from the buy fill to the matching sell fill.
Absolute dollar amounts of the account (starting cash, equity, P&L) are deliberately left out, so they are never sent
to an AI provider. Percentages are rounded to 4 decimal places, ROUND_HALF_EVEN.
"""

from collections.abc import Sequence
from decimal import Decimal

from app.contracts import (
    AnalysisFact,
    Backtest,
    BacktestEquityPoint,
    BacktestStrategy,
    BacktestTrade,
    BuyAndHoldStrategy,
    RsiStrategy,
    SmaCrossoverStrategy,
)
from app.portfolio.allocation import pct, rounded

UNAVAILABLE = "unavailable"


def measured_facts(backtest: Backtest) -> tuple[AnalysisFact, ...]:
    config, metrics = backtest.config, backtest.metrics
    returns = _trade_returns(backtest.trades)
    holding = _holding_days(backtest.trades)
    facts = [
        ("strategy", "Strategy and parameters", _strategy(config.strategy)),
        ("symbols", "Symbols", ", ".join(config.symbols)),
        ("period", "Simulated period", f"{backtest.first_date} to {backtest.last_date} ({backtest.bars} trading days)"),
        ("position_size", "Position size per entry", f"{config.position_size_pct}% of equity, split across symbols"),
        ("costs", "Trading costs", _costs(config.fee_per_trade, config.fee_bps, config.slippage_bps)),
        ("total_return_pct", "Total return", _percent(metrics.total_return_pct)),
        ("annualized_return_pct", "Annualized return", _percent(metrics.annualized_return_pct)),
        ("volatility_pct", "Annualized volatility", _percent(metrics.volatility_pct)),
        ("sharpe_ratio", "Sharpe ratio (risk-free rate 0)", _number(metrics.sharpe_ratio)),
        ("max_drawdown_pct", "Max drawdown", _percent(metrics.max_drawdown_pct)),
        ("max_drawdown_period", "Max drawdown period", _drawdown_period(backtest.equity_curve)),
        ("longest_drawdown_days", "Longest drawdown", f"{_longest_drawdown(backtest.equity_curve)} trading days"),
        ("time_in_market_pct", "Time in market", _percent(_time_in_market(backtest.equity_curve))),
        ("fills", "Fills", str(metrics.trades)),
        ("closed_trades", "Closed trades", str(metrics.closed_trades)),
        ("winning_trades", "Winning closed trades", str(metrics.winning_trades)),
        ("win_rate_pct", "Win rate", _percent(metrics.win_rate_pct)),
        ("average_trade_return_pct", "Average closed trade return", _percent(_mean(returns))),
        ("best_trade_return_pct", "Best closed trade return", _percent(max(returns, default=None))),
        ("worst_trade_return_pct", "Worst closed trade return", _percent(min(returns, default=None))),
        ("average_holding_days", "Average holding period", _days(_mean(holding))),
        ("fees_pct_of_starting_cash", "Total fees as a share of starting cash",
         _percent(pct(metrics.total_fees / config.starting_cash))),
        ("rejected_orders", "Rejected orders", str(len(backtest.rejected_orders))),
        ("open_positions", "Positions still open at the end", str(len(backtest.open_positions))),
    ]
    return tuple(AnalysisFact(id=fact_id, label=label, value=value) for fact_id, label, value in facts)


def _strategy(strategy: BacktestStrategy) -> str:
    match strategy:
        case BuyAndHoldStrategy():
            return "Buy and hold: buy every symbol on the first bar and hold to the end"
        case RsiStrategy():
            return (f"RSI (period {strategy.period}): buy while RSI < {strategy.oversold}, "
                    f"sell while RSI > {strategy.overbought}")
        case SmaCrossoverStrategy():
            return (f"SMA crossover: buy when the {strategy.fast_window}-day average crosses above the "
                    f"{strategy.slow_window}-day average, sell when it crosses below")


def _costs(fee_per_trade: Decimal, fee_bps: Decimal, slippage_bps: Decimal) -> str:
    return f"${fee_per_trade} per fill + {fee_bps} bps fee; {slippage_bps} bps slippage"


def _percent(value: Decimal | None) -> str:
    return UNAVAILABLE if value is None else f"{value}%"


def _number(value: Decimal | None) -> str:
    return UNAVAILABLE if value is None else str(value)


def _days(value: Decimal | None) -> str:
    return UNAVAILABLE if value is None else f"{value.quantize(Decimal('0.1'))} calendar days"


def _mean(values: Sequence[Decimal]) -> Decimal | None:
    return rounded(sum(values, Decimal(0)) / len(values)) if values else None


def _drawdown_period(curve: Sequence[BacktestEquityPoint]) -> str:
    trough = min(range(len(curve)), key=lambda i: (curve[i].drawdown_pct, i))
    if curve[trough].drawdown_pct == 0:
        return "no drawdown"
    peak = max(range(trough + 1), key=lambda i: (curve[i].equity, i))  # the latest close at the running peak
    recovery = next((p.date for p in curve[trough + 1:] if p.equity >= curve[peak].equity), None)
    end = f"recovered {recovery}" if recovery else "not recovered by the last day"
    return f"peak {curve[peak].date}, trough {curve[trough].date}, {end}"


def _longest_drawdown(curve: Sequence[BacktestEquityPoint]) -> int:
    longest = current = 0
    for point in curve:
        current = current + 1 if point.drawdown_pct < 0 else 0
        longest = max(longest, current)
    return longest


def _time_in_market(curve: Sequence[BacktestEquityPoint]) -> Decimal:
    invested = sum(1 for point in curve if point.positions_value > 0)
    return pct(Decimal(invested) / len(curve))


def _trade_returns(trades: Sequence[BacktestTrade]) -> list[Decimal]:
    returns = []
    for trade in trades:
        if trade.realized_pnl is None:
            continue
        cost = trade.notional - trade.fee - trade.realized_pnl
        if cost > 0:
            returns.append(pct(trade.realized_pnl / cost))
    return returns


def _holding_days(trades: Sequence[BacktestTrade]) -> list[Decimal]:
    """Days from each buy to the sell that closes it. The engine buys a symbol once and sells the whole position."""
    opened: dict[str, BacktestTrade] = {}
    days: list[Decimal] = []
    for trade in trades:
        if trade.side == "buy":
            opened[trade.symbol] = trade
        elif (buy := opened.pop(trade.symbol, None)) is not None:
            days.append(Decimal((trade.fill_date - buy.fill_date).days))
    return days
