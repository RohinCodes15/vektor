"""DataFrames shaped like yfinance Ticker.history(auto_adjust=False, actions=False) output."""

from collections.abc import Sequence

import pandas as pd

COLUMNS = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]


def row(open_: float = 10.0, high: float = 12.0, low: float = 9.5, close: float = 11.0,
        adj: float = 10.8, volume: float = 1000) -> list[float]:
    return [open_, high, low, close, adj, volume]


def daily_frame(days: Sequence[str], rows: Sequence[list[float]] | None = None,
                tz: str = "America/New_York") -> pd.DataFrame:
    index = pd.DatetimeIndex(pd.to_datetime(list(days))).tz_localize(tz)
    index.name = "Date"
    return pd.DataFrame(rows if rows is not None else [row() for _ in days], index=index, columns=COLUMNS)
