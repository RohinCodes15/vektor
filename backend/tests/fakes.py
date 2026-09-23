from datetime import date

from app.contracts import MarketDataSource, PriceBar
from app.market_data.provider import ProviderHistory


def make_bar(day: str, close: float = 11.0) -> PriceBar:
    return PriceBar(date=day, open=10, high=max(12, close), low=9.5, close=close, adjusted_close=close, volume=1000)


class FakeProvider:
    """In-memory provider: returns bars inside the requested range, or raises the configured error."""

    source: MarketDataSource = "yahoo_finance"

    def __init__(self, bars: list[PriceBar] | None = None, currency: str | None = "USD",
                 error: Exception | None = None) -> None:
        self.bars = bars if bars is not None else [make_bar("2024-01-02"), make_bar("2024-01-03", 11.5)]
        self.currency = currency
        self.error = error
        self.calls: list[tuple[str, date, date]] = []

    def fetch_daily_history(self, symbol: str, start: date, end: date) -> ProviderHistory:
        self.calls.append((symbol, start, end))
        if self.error is not None:
            raise self.error
        return ProviderHistory(self.currency, tuple(bar for bar in self.bars if start <= bar.date <= end))
