"""Portfolio performance metrics from recorded equity snapshots. Pure: no I/O, Decimal only.

Assumptions (also in backend/README.md):
- Daily series: the last snapshot of each UTC calendar day. Days without a snapshot are absent, not filled.
- Daily return between consecutive observations: (equity - deposits added since the previous observation)
  / previous equity - 1, so deposits are not counted as gains. An observation after zero equity has no return.
- Total return: equity / net deposits - 1, from the latest snapshot.
- Volatility: sample standard deviation of daily returns * sqrt(252); needs at least 2 daily returns.
- Sharpe ratio: mean daily return / its sample standard deviation * sqrt(252), risk-free rate 0; needs at least
  2 daily returns and is undefined (null) when volatility is zero.
- Max drawdown: largest fall from a running peak of the deposit-adjusted index (product of 1 + daily return),
  reported as zero or a negative percentage; needs at least 1 daily return.
- Percentages and the Sharpe ratio are rounded to 4 decimal places, ROUND_HALF_EVEN.
"""

from collections.abc import Sequence
from decimal import Decimal
from itertools import pairwise

from app.contracts import EquitySnapshot

ONE = Decimal(1)


def daily_series(snapshots: Sequence[EquitySnapshot]) -> list[EquitySnapshot]:
    """The last snapshot of each UTC day, oldest first. `snapshots` must be in recording order."""
    last_of_day = {snapshot.taken_at.date(): snapshot for snapshot in snapshots}
    return [last_of_day[day] for day in sorted(last_of_day)]


def daily_returns(series: Sequence[EquitySnapshot]) -> list[Decimal | None]:
    """One deposit-adjusted return per observation after the first; None after a zero-equity observation."""
    returns: list[Decimal | None] = []
    for previous, current in pairwise(series):
        if previous.equity == 0:
            returns.append(None)
            continue
        deposits_added = current.net_deposits - previous.net_deposits
        returns.append((current.equity - deposits_added) / previous.equity - ONE)
    return returns
