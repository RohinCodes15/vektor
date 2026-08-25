"""Grid-search ranking, chronological splits, and overfitting checks. Pure: no I/O, Decimal only.

- Split: the first floor(bars * train_pct / 100) shared trading days train, the rest test. Train days all precede
  test days, so nothing measured on the test segment can influence the ranking.
- Ranking: by the objective on the training segment only. Every objective is better when higher (max drawdown is
  zero or negative, so the shallowest leads). A candidate with an undefined objective (a null Sharpe ratio) is not
  ranked. Ties go to the higher training total return, then to the earlier grid position, so ranking is
  deterministic.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.contracts import BacktestMetrics, BacktestStrategy, OptimizationObjective


@dataclass(frozen=True)
class Split:
    train: tuple[date, ...]
    test: tuple[date, ...]


@dataclass(frozen=True)
class Scored:
    index: int  # position in the grid's combination order
    strategy: BacktestStrategy
    metrics: BacktestMetrics


def split_calendar(calendar: Sequence[date], train_pct: int) -> Split:
    """Chronological split; either side may be empty when the calendar is very short."""
    cut = len(calendar) * train_pct // 100
    return Split(tuple(calendar[:cut]), tuple(calendar[cut:]))


def objective_value(metrics: BacktestMetrics, objective: OptimizationObjective) -> Decimal | None:
    value: Decimal | None = getattr(metrics, objective)
    return value


def rank(scored: Sequence[Scored], objective: OptimizationObjective) -> list[Scored]:
    """Candidates with a defined objective, best first."""
    defined = [s for s in scored if objective_value(s.metrics, objective) is not None]
    return sorted(
        defined,
        key=lambda s: (-_defined(objective_value(s.metrics, objective)), -s.metrics.total_return_pct, s.index),
    )


def _defined(value: Decimal | None) -> Decimal:
    if value is None:  # rank() only passes defined values
        raise ValueError("objective is undefined")
    return value
