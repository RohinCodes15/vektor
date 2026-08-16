from decimal import Decimal

import pytest

from app.backtest.indicators import Indicators, rsi, sma

D = Decimal


def series(*values: float | str) -> list[Decimal]:
    return [D(str(v)) for v in values]


def test_sma_is_undefined_until_the_window_fills_then_a_rolling_mean() -> None:
    assert sma(series(1, 2, 3, 4, 5), 3) == (None, None, D(2), D(3), D(4))


def test_sma_window_of_one_is_the_series_and_short_input_is_all_undefined() -> None:
    assert sma(series(4, 5), 1) == (D(4), D(5))
    assert sma(series(4, 5), 3) == (None, None)
    assert sma([], 3) == ()


def test_rsi_matches_wilders_smoothing_by_hand() -> None:
    # Changes: +2, -1, +1, -2. First averages over 2 changes: gain 1, loss 0.5 -> RSI 100 - 100/3.
    # Next: gain (1*1 + 1)/2 = 1, loss (0.5*1 + 0)/2 = 0.25 -> RS 4 -> RSI 80.
    # Next: gain (1 + 0)/2 = 0.5, loss (0.25 + 2)/2 = 1.125 -> RSI 100 - 100/(1 + 4/9) = 30.7692...
    values = rsi(series(10, 12, 11, 12, 10), 2)
    assert values[:2] == (None, None)
    assert values[2] == D(100) - D(100) / D(3)
    assert values[3] == D(80)
    assert round(values[4], 4) == D("30.7692")  # type: ignore[arg-type]


def test_rsi_is_100_without_losses_and_undefined_without_movement() -> None:
    assert rsi(series(1, 2, 3, 4), 2)[2:] == (D(100), D(100))
    assert rsi(series(5, 5, 5, 5), 2)[2:] == (None, None)
    assert rsi(series(5, 5), 2) == (None, None)


def test_rsi_is_zero_when_prices_only_fall() -> None:
    assert rsi(series(9, 8, 7, 6), 2)[2:] == (D(0), D(0))


@pytest.mark.parametrize("indicator", [sma, rsi])
def test_indicators_are_causal(indicator: object) -> None:
    values = series(10, 11, 9, 12, 13, 12, 8, 9, 15, 14, 13, 16)
    full = indicator(values, 3)  # type: ignore[operator]
    for end in range(len(values)):
        assert indicator(values[: end + 1], 3) == full[: end + 1]  # type: ignore[operator]


@pytest.mark.parametrize("indicator", [sma, rsi])
def test_indicators_reject_a_non_positive_window(indicator: object) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        indicator(series(1, 2), 0)  # type: ignore[operator]


def test_indicators_match_the_plain_functions_and_compute_each_parameter_once() -> None:
    values = [Decimal(v) for v in (10, 11, 13, 12, 9, 14, 15, 11, 10, 12)]
    indicators = Indicators(values)
    assert indicators.sma(3) == sma(values, 3)
    assert indicators.rsi(4) == rsi(values, 4)
    # Memoized: a second request returns the very same series instead of recomputing it.
    assert indicators.sma(3) is indicators.sma(3)
    assert indicators.rsi(4) is indicators.rsi(4)
    assert indicators.sma(4) != indicators.sma(3)
