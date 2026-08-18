from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.market_data.errors import InvalidMarketData
from app.market_data.normalize import drop_unfinished_session, normalize_daily_frame
from tests.market_frames import COLUMNS, daily_frame, row

START, END = date(2024, 1, 1), date(2024, 1, 31)


def test_normalizes_rows_into_typed_bars() -> None:
    frame = daily_frame(["2024-01-02", "2024-01-03"], [row(), row(11, 13, 10.5, 12.5, 12.3, np.int64(2500))])
    bars = normalize_daily_frame(frame, START, END)
    assert [bar.date for bar in bars] == [date(2024, 1, 2), date(2024, 1, 3)]
    assert bars[1].model_dump() == {
        "date": date(2024, 1, 3),
        "open": 11.0,
        "high": 13.0,
        "low": 10.5,
        "close": 12.5,
        "adjusted_close": 12.3,
        "volume": 2500,
    }
    assert type(bars[1].volume) is int and type(bars[1].open) is float


@pytest.mark.parametrize("tz", ["America/New_York", "Asia/Tokyo", "Australia/Sydney", "UTC"])
def test_uses_the_exchange_local_trading_date(tz: str) -> None:
    bars = normalize_daily_frame(daily_frame(["2024-01-02"], tz=tz), START, END)
    assert bars[0].date == date(2024, 1, 2)


def test_accepts_a_timezone_naive_index() -> None:
    frame = daily_frame(["2024-01-02"]).tz_localize(None)
    assert normalize_daily_frame(frame, START, END)[0].date == date(2024, 1, 2)


def test_sorts_bars_and_drops_rows_outside_the_range() -> None:
    frame = daily_frame(
        ["2024-02-01", "2024-01-03", "2023-12-29", "2024-01-02"], [row(), row(), row(-1, -1, -1, -1, -1, -1), row()]
    )
    bars = normalize_daily_frame(frame, START, END)
    assert [bar.date for bar in bars] == [date(2024, 1, 2), date(2024, 1, 3)]


def test_includes_bars_on_the_inclusive_boundaries() -> None:
    frame = daily_frame(["2024-01-01", "2024-01-31"])
    assert [bar.date for bar in normalize_daily_frame(frame, START, END)] == [START, END]


def test_empty_frames_yield_no_bars() -> None:
    assert normalize_daily_frame(pd.DataFrame(columns=COLUMNS), START, END) == ()


def test_rejects_missing_columns() -> None:
    frame = daily_frame(["2024-01-02"]).drop(columns=["Adj Close", "Volume"])
    with pytest.raises(InvalidMarketData, match="missing columns: Adj Close, Volume"):
        normalize_daily_frame(frame, START, END)


@pytest.mark.parametrize("missing", [np.nan, None, pd.NA, "n/a"])
@pytest.mark.parametrize("position", range(6))
def test_rejects_missing_values_instead_of_filling_them(missing: object, position: int) -> None:
    values: list[object] = row()
    values[position] = missing
    frame = daily_frame(["2024-01-02"], [values]).astype(object)
    with pytest.raises(InvalidMarketData, match="missing .* for 2024-01-02"):
        normalize_daily_frame(frame, START, END)


def test_rejects_duplicate_timestamps() -> None:
    frame = daily_frame(["2024-01-02", "2024-01-03", "2024-01-02"])
    with pytest.raises(InvalidMarketData, match="duplicate bars for 2024-01-02"):
        normalize_daily_frame(frame, START, END)


def test_rejects_two_timestamps_on_the_same_trading_date() -> None:
    index = pd.DatetimeIndex(["2024-01-02 00:00", "2024-01-02 16:00"]).tz_localize("America/New_York")
    frame = pd.DataFrame([row(), row()], index=index, columns=COLUMNS)
    with pytest.raises(InvalidMarketData, match="duplicate bars for 2024-01-02"):
        normalize_daily_frame(frame, START, END)


@pytest.mark.parametrize(
    ("values", "reason"),
    [
        (row(open_=0), "open: Input should be greater than 0"),
        (row(adj=-3), "adjusted_close: Input should be greater than 0"),
        (row(high=np.inf), "high: Input should be a finite number"),
        (row(high=9.0), "low <= open, close <= high"),
        (row(low=11.5), "low <= open, close <= high"),
        (row(volume=-5), "volume: Input should be greater than or equal to 0"),
        (row(volume=10.5), "volume: Input should be a valid integer"),
    ],
)
def test_rejects_invalid_prices_and_volume(values: list[float], reason: str) -> None:
    with pytest.raises(InvalidMarketData) as error:
        normalize_daily_frame(daily_frame(["2024-01-02"], [values]), START, END)
    assert error.value.message.startswith("Provider returned an invalid bar for 2024-01-02: ")
    assert reason in error.value.message


def test_ignores_invalid_rows_outside_the_range() -> None:
    frame = daily_frame(["2023-12-29", "2024-01-02"], [row(open_=np.nan), row()])
    assert len(normalize_daily_frame(frame, START, END)) == 1


def test_rejects_unparseable_timestamps() -> None:
    frame = pd.DataFrame([row()], index=pd.Index(["not-a-date"]), columns=COLUMNS)
    with pytest.raises(InvalidMarketData, match="invalid timestamp"):
        normalize_daily_frame(frame, START, END)


def test_rejects_missing_timestamps() -> None:
    frame = pd.DataFrame([row()], index=pd.DatetimeIndex([pd.NaT]), columns=COLUMNS)
    with pytest.raises(InvalidMarketData, match="invalid timestamp"):
        normalize_daily_frame(frame, START, END)


def unfinished_row() -> list[float]:
    """Yahoo's row for a session that is still trading or not yet finalized: no adjusted close."""
    values = row()
    values[4] = np.nan
    return values


def test_drops_the_newest_row_when_it_is_an_unfinished_live_session() -> None:
    frame = daily_frame(["2024-01-02", "2024-01-03"], [row(), unfinished_row()])
    kept, dropped = drop_unfinished_session(frame, live_from=date(2024, 1, 3))
    assert dropped is True
    assert [bar.date for bar in normalize_daily_frame(kept, START, END)] == [date(2024, 1, 2)]


def test_keeps_an_incomplete_historical_row_so_it_is_still_rejected() -> None:
    frame = daily_frame(["2024-01-02", "2024-01-03"], [row(), unfinished_row()])
    kept, dropped = drop_unfinished_session(frame, live_from=date(2024, 1, 4))
    assert dropped is False
    with pytest.raises(InvalidMarketData, match="missing adjusted_close for 2024-01-03"):
        normalize_daily_frame(kept, START, END)


def test_never_drops_an_incomplete_row_that_is_not_the_newest() -> None:
    frame = daily_frame(["2024-01-02", "2024-01-03"], [unfinished_row(), row()])
    kept, dropped = drop_unfinished_session(frame, live_from=date(2024, 1, 1))
    assert dropped is False
    with pytest.raises(InvalidMarketData, match="missing adjusted_close for 2024-01-02"):
        normalize_daily_frame(kept, START, END)
