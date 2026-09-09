"""Backtest performance from the daily equity curve and closed trades. Pure: no I/O, Decimal only.

Formulas (also in backend/README.md), with E_0..E_n the equity at each close and E_0 the starting cash:
- Daily return r_t = E_t / E_(t-1) - 1 (a day after zero equity has no return).
- Total return: E_n / starting cash - 1.
- Annualized return: (E_n / starting cash) ^ (252 / n) - 1, with n the number of daily returns. -100% when the
  account is worth nothing.
- Volatility: sample standard deviation of daily returns * sqrt(252); needs at least 2 returns.
- Sharpe ratio: mean daily return / sample standard deviation * sqrt(252), risk-free rate 0; needs at least 2
  returns and is undefined when volatility is zero (for example, when nothing was ever bought).
- Drawdown at t: E_t / max(E_0..E_t) - 1. Max drawdown is the lowest, zero or negative.
- Win rate: closed trades (sells) with realized P&L > 0 / closed trades; undefined without a closed trade.
- Percentages and the Sharpe ratio are rounded to 4 decimal places, ROUND_HALF_EVEN.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from itertools import accumulate, pairwise

from app.portfolio.allocation import pct, rounded
from app.portfolio.analytics import TRADING_DAYS_PER_YEAR, mean, sample_stdev

ONE = Decimal(1)
ANNUALIZER = Decimal(TRADING_DAYS_PER_YEAR).sqrt()


@dataclass(frozen=True)
class Performance:
    total_return_pct: Decimal
    annualized_return_pct: Decimal | None
    volatility_pct: Decimal | None
    max_drawdown_pct: Decimal
    sharpe_ratio: Decimal | None
    win_rate_pct: Decimal | None
    closed_trades: int
    winning_trades: int
    drawdowns_pct: tuple[Decimal, ...]  # one per equity point
    warnings: tuple[str, ...]  # why each undefined metric is null


def compute_performance(
    starting_cash: Decimal, equity: Sequence[Decimal], realized_pnl: Sequence[Decimal]
) -> Performance:
    """`equity` has one value per bar (at least one); `realized_pnl` has one value per closed trade."""
    returns = [today / previous - ONE for previous, today in pairwise(equity) if previous > 0]
    stdev = sample_stdev(returns)
    # The running peak is at least the starting cash, which is positive.
    drawdowns = tuple(pct(e / peak - ONE) for e, peak in zip(equity, accumulate(equity, max), strict=True))
    winners = sum(1 for pnl in realized_pnl if pnl > 0)
    warnings: list[str] = []
    if len(equity) < 2:
        warnings.append("Annualized return needs at least 1 daily return.")
    if stdev is None:
        warnings.append("Volatility and Sharpe ratio need at least 2 daily returns.")
    elif stdev == 0:
        warnings.append("Sharpe ratio is undefined: daily returns have zero volatility.")
    if not realized_pnl:
        warnings.append("Win rate is undefined: no trade was closed.")
    return Performance(
        total_return_pct=pct(equity[-1] / starting_cash - ONE),
        annualized_return_pct=_annualized(equity[-1] / starting_cash, len(equity) - 1),
        volatility_pct=pct(stdev * ANNUALIZER) if stdev is not None else None,
        max_drawdown_pct=min(drawdowns),
        sharpe_ratio=rounded(mean(returns) / stdev * ANNUALIZER) if stdev else None,
        win_rate_pct=pct(Decimal(winners) / len(realized_pnl)) if realized_pnl else None,
        closed_trades=len(realized_pnl),
        winning_trades=winners,
        drawdowns_pct=drawdowns,
        warnings=tuple(warnings),
    )


def _annualized(growth: Decimal, periods: int) -> Decimal | None:
    if periods < 1:
        return None
    if growth <= 0:
        return pct(-ONE)
    return pct((growth.ln() * TRADING_DAYS_PER_YEAR / periods).exp() - ONE)
