"""Relative performance of compared strategies. Pure: no I/O, Decimal only.

- Differences: a strategy's metric minus the baseline's (the first strategy), only when both are defined.
- Leaders: per metric, the strategies with the best value among those where it is defined. Higher is better except
  volatility; max drawdown is zero or negative, so higher (closer to zero) is better. No leader when fewer than 2
  strategies have the metric or every one of them is equal, since then there is nothing to compare.
"""

from collections.abc import Sequence
from decimal import Decimal
from typing import Literal, get_args

from app.contracts import BacktestMetrics, ComparisonMetric, MetricDifferences, MetricLeader

LOWER_IS_BETTER: frozenset[ComparisonMetric] = frozenset({"volatility_pct"})
METRICS: tuple[ComparisonMetric, ...] = get_args(ComparisonMetric)


def differences(metrics: BacktestMetrics, baseline: BacktestMetrics) -> MetricDifferences:
    values: dict[str, Decimal | None] = {}
    for metric in METRICS:
        mine, theirs = getattr(metrics, metric), getattr(baseline, metric)
        values[metric] = None if mine is None or theirs is None else mine - theirs
    return MetricDifferences(**values)


def leaders(metrics: Sequence[BacktestMetrics | None]) -> list[MetricLeader]:
    return [_leader(metric, metrics) for metric in METRICS]


def _leader(metric: ComparisonMetric, metrics: Sequence[BacktestMetrics | None]) -> MetricLeader:
    better: Literal["higher", "lower"] = "lower" if metric in LOWER_IS_BETTER else "higher"
    values = {i: getattr(m, metric) for i, m in enumerate(metrics) if m is not None and getattr(m, metric) is not None}
    if len(values) < 2:
        return MetricLeader(
            metric=metric, better=better, leaders=[], reason="Fewer than 2 strategies have this metric."
        )
    best = min(values.values()) if better == "lower" else max(values.values())
    tied = [i for i, value in values.items() if value == best]
    if len(tied) == len(values):
        return MetricLeader(metric=metric, better=better, leaders=[], reason="Every compared strategy is equal.")
    return MetricLeader(metric=metric, better=better, leaders=tied, reason=None)
