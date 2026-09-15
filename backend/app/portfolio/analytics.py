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
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from itertools import pairwise

from app.contracts import EquitySnapshot

TRADING_DAYS_PER_YEAR = 252
METRIC_TICK = Decimal("0.0001")
ONE = Decimal(1)


@dataclass(frozen=True)
class Metrics:
    daily_observations: int
    total_return_pct: Decimal | None
    latest_daily_return_pct: Decimal | None
    volatility_pct: Decimal | None
    max_drawdown_pct: Decimal | None
    sharpe_ratio: Decimal | None


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


def compute_metrics(snapshots: Sequence[EquitySnapshot]) -> Metrics:
    if not snapshots:
        return Metrics(0, None, None, None, None, None)
    series = daily_series(snapshots)
    returns = daily_returns(series)
    valid = [r for r in returns if r is not None]
    latest = snapshots[-1]
    stdev = _sample_stdev(valid)
    annualizer = Decimal(TRADING_DAYS_PER_YEAR).sqrt()
    return Metrics(
        daily_observations=len(series),
        total_return_pct=_pct(latest.equity / latest.net_deposits - ONE) if latest.net_deposits > 0 else None,
        latest_daily_return_pct=_pct(returns[-1]) if returns and returns[-1] is not None else None,
        volatility_pct=_pct(stdev * annualizer) if stdev is not None else None,
        max_drawdown_pct=_pct(_max_drawdown(valid)) if valid else None,
        sharpe_ratio=_round(_mean(valid) / stdev * annualizer) if stdev else None,
    )


def _mean(values: Sequence[Decimal]) -> Decimal:
    return sum(values, Decimal(0)) / len(values)


def _sample_stdev(values: Sequence[Decimal]) -> Decimal | None:
    if len(values) < 2:
        return None
    mean = _mean(values)
    return (sum(((v - mean) ** 2 for v in values), Decimal(0)) / (len(values) - 1)).sqrt()


def _max_drawdown(returns: Sequence[Decimal]) -> Decimal:
    index = peak = ONE
    worst = Decimal(0)
    for r in returns:
        index *= ONE + r
        peak = max(peak, index)
        worst = min(worst, index / peak - ONE)
    return worst


def _pct(fraction: Decimal) -> Decimal:
    return _round(fraction * 100)


def _round(value: Decimal) -> Decimal:
    return value.quantize(METRIC_TICK, ROUND_HALF_EVEN)
