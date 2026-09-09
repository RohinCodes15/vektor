"""Strategy signals from closing prices. Pure: no I/O, Decimal only.

signal_series(strategy, closes)[i] is the signal at the close of bar i, computed from closes[0..i] only, so
truncating the input never changes an earlier signal. The engine fills it no earlier than the next bar's open.
- Buy & hold: "buy" at bar 0, nothing after.
- SMA crossover: "buy" when fast - slow turns from <= 0 to > 0, "sell" when it turns from >= 0 to < 0. The first
  possible signal is at i = slow_window, the first bar after both averages exist.
- RSI: "buy" while RSI < oversold, "sell" while RSI > overbought; first possible at i = period.
The engine ignores a "buy" while holding and a "sell" while flat.
"""

from collections.abc import Sequence
from decimal import Decimal
from itertools import pairwise
from typing import Literal

from app.backtest.indicators import rsi, sma
from app.contracts import BacktestStrategy, BuyAndHoldStrategy, RsiStrategy, SmaCrossoverStrategy

Signal = Literal["buy", "sell"]


def warmup_bars(strategy: BacktestStrategy) -> int:
    """Bars needed before the first possible signal can fill: the signal bar's index plus two (it and the next)."""
    match strategy:
        case BuyAndHoldStrategy():
            return 2
        case SmaCrossoverStrategy():
            return strategy.slow_window + 2
        case RsiStrategy():
            return strategy.period + 2


def signal_series(strategy: BacktestStrategy, closes: Sequence[Decimal]) -> tuple[Signal | None, ...]:
    match strategy:
        case BuyAndHoldStrategy():
            return tuple("buy" if i == 0 else None for i in range(len(closes)))
        case SmaCrossoverStrategy():
            return _sma_crossover(strategy, closes)
        case RsiStrategy():
            return _rsi_levels(strategy, closes)


def _sma_crossover(strategy: SmaCrossoverStrategy, closes: Sequence[Decimal]) -> tuple[Signal | None, ...]:
    fast = sma(closes, strategy.fast_window)
    slow = sma(closes, strategy.slow_window)
    spread = [f - s if f is not None and s is not None else None for f, s in zip(fast, slow, strict=True)]
    signals: list[Signal | None] = [None] * min(len(closes), 1)
    for previous, current in pairwise(spread):
        signals.append(_crossing(previous, current))
    return tuple(signals)


def _crossing(previous: Decimal | None, current: Decimal | None) -> Signal | None:
    if previous is None or current is None:
        return None
    if previous <= 0 < current:
        return "buy"
    if previous >= 0 > current:
        return "sell"
    return None


def _rsi_levels(strategy: RsiStrategy, closes: Sequence[Decimal]) -> tuple[Signal | None, ...]:
    def level(value: Decimal | None) -> Signal | None:
        if value is None:
            return None
        if value < strategy.oversold:
            return "buy"
        return "sell" if value > strategy.overbought else None

    return tuple(level(value) for value in rsi(closes, strategy.period))
