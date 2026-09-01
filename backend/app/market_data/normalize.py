"""Turn a provider's daily OHLCV frame into validated PriceBar contracts. Pure: no I/O."""

import math
from datetime import date
from numbers import Integral
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from app.contracts import PriceBar
from app.market_data.errors import InvalidMarketData
from app.validation import summarize_errors

if TYPE_CHECKING:
    from pandas import DataFrame

# PriceBar field -> provider column (yfinance with auto_adjust=False).
COLUMNS = {
    "open": "Open",
    "high": "High",
    "low": "Low",
    "close": "Close",
    "adjusted_close": "Adj Close",
    "volume": "Volume",
}


def normalize_daily_frame(frame: "DataFrame", start: date, end: date) -> tuple[PriceBar, ...]:
    """Validate every bar dated within [start, end]; bars outside it are ignored.

    Any missing value, duplicate date, or invalid price rejects the whole frame: data is never filled or repaired.
    """
    if frame.empty:
        return ()
    missing_columns = [column for column in COLUMNS.values() if column not in frame.columns]
    if missing_columns:
        raise InvalidMarketData(f"Provider response is missing columns: {', '.join(missing_columns)}.")

    bars: list[PriceBar] = []
    seen: set[date] = set()
    rows = frame[list(COLUMNS.values())].itertuples(index=False, name=None)
    for timestamp, values in zip(frame.index, rows, strict=True):
        day = _trading_date(timestamp)
        if not start <= day <= end:
            continue
        if day in seen:
            raise InvalidMarketData(f"Provider returned duplicate bars for {day.isoformat()}.")
        seen.add(day)
        bars.append(_to_bar(day, dict(zip(COLUMNS, values, strict=True))))
    return tuple(sorted(bars, key=lambda bar: bar.date))


def _trading_date(timestamp: Any) -> date:
    """The bar's calendar date in the exchange's timezone (yfinance indexes daily bars at local midnight)."""
    try:
        return date(timestamp.year, timestamp.month, timestamp.day)
    except (AttributeError, TypeError, ValueError):
        raise InvalidMarketData("Provider returned a bar with an invalid timestamp.") from None


def _to_bar(day: date, values: dict[str, Any]) -> PriceBar:
    fields: dict[str, Any] = {"date": day}
    for name, value in values.items():
        number = _number(value)
        if number is None:
            raise InvalidMarketData(f"Provider returned missing {name} for {day.isoformat()}.")
        fields[name] = number
    try:
        return PriceBar(**fields)
    except ValidationError as error:
        raise InvalidMarketData(
            f"Provider returned an invalid bar for {day.isoformat()}: {summarize_errors(error.errors())}."
        ) from None


def _number(value: Any) -> int | float | None:
    """Native int/float, or None when the value is missing (None, NaN, NA, or not numeric)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, Integral):
        return int(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number  # NaN is missing
