"""Shared API contracts (v1). Coordinated with frontend/ — see AGENTS.md before changing.

Simulation models are contracts only; no endpoints serve them yet.
Market history models back the read-only GET /api/v1/market/history endpoint.
"""

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TradingMode = Literal["paper"]
PriceInterval = Literal["1d"]

# Yahoo-style tickers: AAPL, BRK-B, BRK.B, 7203.T, EURUSD=X, GC=F, and indices such as ^GSPC.
_SYMBOL = re.compile(r"\^?[A-Z0-9][A-Z0-9.=-]{0,14}")


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HealthResponse(Contract):
    status: Literal["ok"]
    app: str
    version: str
    environment: str
    trading_mode: TradingMode


class SimulationCreate(Contract):
    symbols: list[str] = Field(min_length=1, max_length=50)
    starting_cash: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    start: datetime
    end: datetime
    strategy: str = Field(min_length=1, max_length=100)


class Simulation(Contract):
    id: UUID
    status: Literal["pending", "running", "completed", "failed"]
    mode: TradingMode = "paper"
    config: SimulationCreate
    created_at: datetime


class PaperOrder(Contract):
    symbol: str = Field(min_length=1, max_length=10)
    side: Literal["buy", "sell"]
    quantity: Decimal = Field(gt=0)
    type: Literal["market", "limit"] = "market"
    limit_price: Decimal | None = Field(default=None, gt=0)


class ErrorResponse(Contract):
    detail: str


class MarketHistoryQuery(Contract):
    """Query for daily OHLCV history. `start` and `end` are inclusive calendar dates."""

    symbol: str
    start: date
    end: date
    interval: PriceInterval = "1d"

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        symbol = value.strip().upper()
        if not _SYMBOL.fullmatch(symbol):
            raise ValueError(
                "symbol must be 1-15 letters, digits, '.', '-' or '=', optionally prefixed with '^'"
            )
        return symbol

    @model_validator(mode="after")
    def check_date_range(self) -> Self:
        if self.start > self.end:
            raise ValueError("start must be on or before end")
        if self.start > datetime.now(UTC).date():
            raise ValueError("start cannot be in the future")
        return self


PositivePrice = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class PriceBar(Contract):
    """One daily bar. `date` is the trading day in the exchange's local calendar."""

    date: date
    open: PositivePrice
    high: PositivePrice
    low: PositivePrice
    close: PositivePrice
    # Close adjusted for splits and dividends, as reported by the provider.
    adjusted_close: PositivePrice
    volume: int = Field(ge=0)

    @model_validator(mode="after")
    def check_price_range(self) -> Self:
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError("prices must satisfy low <= open, close <= high")
        return self
