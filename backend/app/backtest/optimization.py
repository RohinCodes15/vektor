"""Grid-search ranking, chronological splits, and overfitting checks. Pure: no I/O, Decimal only.

- Split: the first floor(bars * train_pct / 100) shared trading days train, the rest test. Train days all precede
  test days, so nothing measured on the test segment can influence the ranking.
- Ranking: by the objective on the training segment only. Every objective is better when higher (max drawdown is
  zero or negative, so the shallowest leads). A candidate with an undefined objective (a null Sharpe ratio) is not
  ranked. Ties go to the higher training total return, then to the earlier grid position, so ranking is
  deterministic.
- Overfitting flags are warning signs computed from train vs test results and the grid shape; they are not proof.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.contracts import (
    BacktestMetrics,
    BacktestStrategy,
    OptimizationObjective,
    OverfittingFlag,
    OverfittingReport,
    ParameterGrid,
    RsiStrategy,
    SmaCrossoverGrid,
    SmaCrossoverStrategy,
)

# Fewer closed training trades than this is weak evidence for any ranking.
MIN_CLOSED_TRADES = 5
# More candidates than this makes a lucky winner likely (multiple testing).
MANY_CANDIDATES = 50
TWO = Decimal(2)


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


def overfitting_report(
    strategy: BacktestStrategy, grid: ParameterGrid, candidates: int, train: BacktestMetrics, test: BacktestMetrics
) -> OverfittingReport:
    return OverfittingReport(
        annualized_return_gap_pct=_gap(test.annualized_return_pct, train.annualized_return_pct),
        sharpe_gap=_gap(test.sharpe_ratio, train.sharpe_ratio),
        max_drawdown_gap_pct=test.max_drawdown_pct - train.max_drawdown_pct,
        flags=_flags(strategy, grid, candidates, train, test),
    )


def _flags(
    strategy: BacktestStrategy, grid: ParameterGrid, candidates: int, train: BacktestMetrics, test: BacktestMetrics
) -> list[OverfittingFlag]:
    flags: list[OverfittingFlag] = []
    if train.total_return_pct > 0 >= test.total_return_pct:
        flags.append(OverfittingFlag(
            code="return_reversal",
            message="The selected parameters gained on the training data but not on the test data.",
        ))
    if train.sharpe_ratio is not None and train.sharpe_ratio > 0 and (
        test.sharpe_ratio is None or test.sharpe_ratio < train.sharpe_ratio / TWO
    ):
        flags.append(OverfittingFlag(
            code="sharpe_decay",
            message="The test Sharpe ratio is undefined or less than half of the training Sharpe ratio.",
        ))
    if train.closed_trades < MIN_CLOSED_TRADES:
        flags.append(OverfittingFlag(
            code="few_trades",
            message=f"Only {train.closed_trades} closed training trades: too few to tell skill from chance.",
        ))
    edges = _edges(strategy, grid)
    if edges:
        flags.append(OverfittingFlag(
            code="edge_of_grid",
            message=f"{', '.join(edges)} sits at the edge of the searched range; the best value may lie outside it.",
        ))
    if candidates > MANY_CANDIDATES:
        flags.append(OverfittingFlag(
            code="many_candidates",
            message=f"{candidates} combinations were tried; the more are tried, the likelier the best one is luck.",
        ))
    return flags


def _edges(strategy: BacktestStrategy, grid: ParameterGrid) -> list[str]:
    """Names of the selected parameters equal to the smallest or largest searched value (dimensions with 2+ values)."""
    if isinstance(grid, SmaCrossoverGrid) and isinstance(strategy, SmaCrossoverStrategy):
        dimensions: list[tuple[str, Sequence[object], object]] = [
            ("fast_window", grid.fast_windows, strategy.fast_window),
            ("slow_window", grid.slow_windows, strategy.slow_window),
        ]
    elif isinstance(strategy, RsiStrategy) and not isinstance(grid, SmaCrossoverGrid):
        dimensions = [
            ("period", grid.periods, strategy.period),
            ("oversold", grid.oversold, strategy.oversold),
            ("overbought", grid.overbought, strategy.overbought),
        ]
    else:
        return []
    return [name for name, values, value in dimensions if len(values) > 1 and value in (values[0], values[-1])]


def _gap(test: Decimal | None, train: Decimal | None) -> Decimal | None:
    return test - train if test is not None and train is not None else None


def _defined(value: Decimal | None) -> Decimal:
    if value is None:  # rank() only passes defined values
        raise ValueError("objective is undefined")
    return value
