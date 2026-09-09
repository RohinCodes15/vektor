from decimal import Decimal

import pytest

from app.backtest.indicators import sma

D = Decimal


def series(*values: float | str) -> list[Decimal]:
    return [D(str(v)) for v in values]


def test_sma_is_undefined_until_the_window_fills_then_a_rolling_mean() -> None:
    assert sma(series(1, 2, 3, 4, 5), 3) == (None, None, D(2), D(3), D(4))


def test_sma_window_of_one_is_the_series_and_short_input_is_all_undefined() -> None:
    assert sma(series(4, 5), 1) == (D(4), D(5))
    assert sma(series(4, 5), 3) == (None, None)
    assert sma([], 3) == ()


@pytest.mark.parametrize("indicator", [sma])
def test_indicators_are_causal(indicator: object) -> None:
    values = series(10, 11, 9, 12, 13, 12, 8, 9, 15, 14, 13, 16)
    full = indicator(values, 3)  # type: ignore[operator]
    for end in range(len(values)):
        assert indicator(values[: end + 1], 3) == full[: end + 1]  # type: ignore[operator]


@pytest.mark.parametrize("indicator", [sma])
def test_indicators_reject_a_non_positive_window(indicator: object) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        indicator(series(1, 2), 0)  # type: ignore[operator]
