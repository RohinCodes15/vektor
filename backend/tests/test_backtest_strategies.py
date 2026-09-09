from decimal import Decimal

import pytest

from app.backtest.strategies import signal_series, warmup_bars
from app.contracts import BacktestStrategy, BuyAndHoldStrategy, RsiStrategy, SmaCrossoverStrategy

BUY_AND_HOLD = BuyAndHoldStrategy(kind="buy_and_hold")
SMA = SmaCrossoverStrategy(kind="sma_crossover", fast_window=2, slow_window=3)
RSI = RsiStrategy(kind="rsi", period=2, oversold=Decimal(30), overbought=Decimal(70))


def closes(*values: float) -> list[Decimal]:
    return [Decimal(str(v)) for v in values]


def test_buy_and_hold_buys_on_the_first_bar_only() -> None:
    assert signal_series(BUY_AND_HOLD, closes(1, 2, 3)) == ("buy", None, None)
    assert signal_series(BUY_AND_HOLD, []) == ()


def test_sma_crossover_signals_only_on_crossings() -> None:
    # fast(2) - slow(3): bar 2: 0, bar 3: +0.5 (cross up), bar 4: 0 (touch, no cross), bar 5: -2 (cross down),
    # bar 6: 0 (touch from below, no cross).
    assert signal_series(SMA, closes(10, 10, 10, 13, 7, 7, 7)) == (None, None, None, "buy", None, "sell", None)


def test_sma_crossover_needs_both_averages_on_the_previous_bar() -> None:
    # Bar 2 is the first with a slow average, so it cannot be a crossing even though fast > slow there.
    assert signal_series(SMA, closes(1, 2, 3)) == (None, None, None)
    assert signal_series(SMA, closes(5)) == (None,)


def test_rsi_buys_below_oversold_and_sells_above_overbought() -> None:
    # RSI(2): bar 2: 66.7 (none), bar 3: 80 (sell), bar 4: 30.8 (none), bar 5: 13.8 (buy).
    assert signal_series(RSI, closes(10, 12, 11, 12, 10, 8)) == (None, None, None, "sell", None, "buy")


def test_rsi_thresholds_are_strict_and_flat_prices_never_signal() -> None:
    at_threshold = RsiStrategy(kind="rsi", period=2, oversold=Decimal(20), overbought=Decimal(80))
    assert signal_series(at_threshold, closes(10, 12, 11, 12))[3] is None  # RSI exactly 80
    assert signal_series(RSI, closes(5, 5, 5, 5)) == (None, None, None, None)


def test_warmup_counts_the_signal_bar_and_the_fill_bar() -> None:
    assert warmup_bars(BUY_AND_HOLD) == 2
    assert warmup_bars(SMA) == 5  # first signal at bar 3, filled at bar 4
    assert warmup_bars(RSI) == 4  # first signal at bar 2, filled at bar 3


@pytest.mark.parametrize("strategy", [BUY_AND_HOLD, SMA, RSI])
def test_signals_never_depend_on_later_bars(strategy: BacktestStrategy) -> None:
    history = closes(10, 12, 11, 12, 10, 8, 9, 13, 14, 12, 7, 6, 9, 15, 11)
    full = signal_series(strategy, history)
    for end in range(len(history)):
        prefix = history[: end + 1]
        assert signal_series(strategy, prefix) == full[: end + 1]
        shocked = [*prefix, Decimal(1000)]  # an extreme next close cannot change any signal before it
        assert signal_series(strategy, shocked)[: end + 1] == full[: end + 1]
