from datetime import date
from decimal import Decimal

from app.backtest.prices import Bar, adjust, align
from app.contracts import PriceBar

D = Decimal


def bar(day: str, close: float = 100.0, adjusted: float | None = None) -> PriceBar:
    return PriceBar(
        date=day, open=close - 1, high=close + 2, low=close - 3, close=close,
        adjusted_close=close if adjusted is None else adjusted, volume=1000,
    )


def test_unadjusted_bars_keep_their_prices() -> None:
    assert adjust(bar("2024-01-02")) == Bar(date(2024, 1, 2), D("99.0000"), D("102.0000"), D("97.0000"), D("100.0000"))


def test_every_price_is_scaled_by_the_adjustment_factor_and_rounded() -> None:
    adjusted = adjust(bar("2024-01-02", close=100.0, adjusted=98.76543))
    # factor 0.9876543: open 99 -> 97.7777757, high 102 -> 100.7407386, low 97 -> 95.8024671.
    assert adjusted == Bar(date(2024, 1, 2), D("97.7778"), D("100.7407"), D("95.8025"), D("98.7654"))
    assert adjusted is not None and adjusted.low <= adjusted.open <= adjusted.high


def test_prices_that_round_to_zero_are_unusable() -> None:
    tiny = PriceBar(date="2024-01-02", open=1, high=1, low=1, close=1, adjusted_close=0.00004, volume=1)
    assert adjust(tiny) is None


def test_align_keeps_only_dates_every_symbol_traded() -> None:
    a = [Bar(date(2024, 1, d), D(1), D(1), D(1), D(d)) for d in (2, 3, 4, 5)]
    b = [Bar(date(2024, 1, d), D(2), D(2), D(2), D(d)) for d in (3, 5, 6)]
    aligned = align({"A": a, "B": b})
    assert aligned.calendar == (date(2024, 1, 3), date(2024, 1, 5))
    assert [x.close for x in aligned.bars["A"]] == [D(3), D(5)]
    assert [x.close for x in aligned.bars["B"]] == [D(3), D(5)]


def test_align_of_nothing_is_empty() -> None:
    assert align({}).calendar == ()
