"""Adjusted daily bars on one shared calendar. Pure: no I/O, Decimal only.

- Adjustment: every price of a bar is multiplied by adjusted_close / close, so the series includes splits and
  dividends (a total-return series) and a corporate action never looks like a price jump. Prices are then rounded
  to 4 decimal places, ROUND_HALF_EVEN. Rounding and scaling are monotonic, so low <= open, close <= high still holds.
- Calendar: only dates on which every symbol has a bar. A date missing for one symbol is dropped for all of them,
  never filled.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

from app.contracts import PriceBar
from app.portfolio.accounting import PRICE_TICK


@dataclass(frozen=True)
class Bar:
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


def adjust(bar: PriceBar) -> Bar | None:
    """The bar in adjusted prices, or None when a price rounds to zero (too small to trade)."""
    factor = Decimal(str(bar.adjusted_close)) / Decimal(str(bar.close))
    prices = [
        (Decimal(str(price)) * factor).quantize(PRICE_TICK, ROUND_HALF_EVEN)
        for price in (bar.open, bar.high, bar.low, bar.close)
    ]
    if min(prices) <= 0:
        return None
    return Bar(bar.date, *prices)


@dataclass(frozen=True)
class Aligned:
    calendar: tuple[date, ...]
    bars: dict[str, tuple[Bar, ...]]  # bars[symbol][i] is on calendar[i]


def align(series: Mapping[str, Sequence[Bar]]) -> Aligned:
    by_date = {symbol: {bar.date: bar for bar in bars} for symbol, bars in series.items()}
    common = set.intersection(*(set(days) for days in by_date.values())) if by_date else set()
    calendar = tuple(sorted(common))
    return Aligned(calendar, {symbol: tuple(days[d] for d in calendar) for symbol, days in by_date.items()})
