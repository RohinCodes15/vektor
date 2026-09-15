"""Shared API contracts (v1). Coordinated with frontend/ — see AGENTS.md before changing.

Simulation models are contracts only; no endpoints serve them yet.
Market history models back the read-only GET /api/v1/market/history endpoint.
Portfolio models back the paper portfolio endpoints under /api/v1/portfolios; equity snapshots and analytics live
under the same prefix. Money is a Decimal, serialized as a
JSON string: cash, cost and P&L have 2 decimal places, prices 4, percentages 2 (see app/portfolio/accounting.py).
"""

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

TradingMode = Literal["paper"]
PriceInterval = Literal["1d"]
MarketDataSource = Literal["yahoo_finance"]

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


class MarketHistoryResponse(Contract):
    """Read-only daily history for one symbol, exactly as fetched from the provider."""

    symbol: str
    interval: PriceInterval
    start: date
    end: date
    currency: str | None
    source: MarketDataSource
    # True when served from the local cache; `fetched_at` is when the provider returned the data.
    cached: bool
    fetched_at: AwareDatetime
    bars: list[PriceBar]

    @model_validator(mode="after")
    def check_bars(self) -> Self:
        dates = [bar.date for bar in self.bars]
        if any(earlier >= later for earlier, later in zip(dates, dates[1:], strict=False)):
            raise ValueError("bars must be in ascending date order without duplicates")
        if dates and (dates[0] < self.start or dates[-1] > self.end):
            raise ValueError("bars must fall within start and end")
        return self


# Paper portfolios. Cash is virtual US dollars; nothing here reaches a broker.
PortfolioCurrency = Literal["USD"]
OrderSide = Literal["buy", "sell"]

# Tradable tickers only: no index (^GSPC), future (GC=F) or currency pair (EURUSD=X), which have no share price.
_TRADABLE_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9.-]{0,14}")
PortfolioName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


def _canonical(value: Decimal) -> Decimal:
    """Same value without trailing zeros or exponent: 1.50 -> 1.5, 1E+1 -> 10."""
    return Decimal(format(value.normalize(), "f"))


class PortfolioCreate(Contract):
    name: PortfolioName
    starting_cash: Decimal = Field(gt=0, max_digits=14, decimal_places=2)

    @field_validator("starting_cash")
    @classmethod
    def to_cents(cls, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"))  # exact: at most 2 decimal places were accepted


class PortfolioUpdate(Contract):
    """Only the name can change. Cash moves only through orders, so balances are never edited by hand."""

    name: PortfolioName


class Portfolio(Contract):
    id: UUID
    name: str
    mode: TradingMode = "paper"
    currency: PortfolioCurrency
    starting_cash: Decimal
    cash: Decimal
    # Sum of the realized P&L of every sell.
    realized_pnl: Decimal
    created_at: AwareDatetime
    updated_at: AwareDatetime


class PaperOrder(Contract):
    """A market order, filled in full at the latest completed daily close or rejected; never partially filled.

    `client_order_id` makes submission idempotent: resending it returns the original transaction.
    """

    client_order_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")
    symbol: str
    side: OrderSide
    quantity: Decimal = Field(gt=0, max_digits=16, decimal_places=6)

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        symbol = value.strip().upper()
        if not _TRADABLE_SYMBOL.fullmatch(symbol):
            raise ValueError("symbol must be a ticker of 1-15 letters, digits, '.' or '-'")
        return symbol

    @field_validator("quantity")
    @classmethod
    def canonical_quantity(cls, value: Decimal) -> Decimal:
        return _canonical(value)


class Transaction(Contract):
    """One executed paper order. Prices are the provider's daily close for `price_date`."""

    id: UUID
    portfolio_id: UUID
    client_order_id: str
    symbol: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    price_date: date
    # quantity * price, rounded to cents. Cash moves by exactly this amount; there are no fees.
    notional: Decimal
    # Sells only: notional minus the average cost of the shares sold.
    realized_pnl: Decimal | None
    executed_at: AwareDatetime


class Holding(Contract):
    """One open position. Price fields are null when no recent market price exists (never estimated)."""

    symbol: str
    quantity: Decimal
    # Total average cost of the shares still held.
    cost_basis: Decimal
    last_price: Decimal | None
    price_date: date | None
    market_value: Decimal | None
    unrealized_pnl: Decimal | None
    # Share of equity; null when equity is unknown or zero.
    allocation_pct: Decimal | None


class PortfolioHoldings(Contract):
    """Portfolio valued at the latest completed daily closes. Totals are null when any holding has no price."""

    portfolio_id: UUID
    currency: PortfolioCurrency
    cash: Decimal
    positions_value: Decimal | None
    equity: Decimal | None
    unrealized_pnl: Decimal | None
    realized_pnl: Decimal
    cash_allocation_pct: Decimal | None
    valued_at: AwareDatetime
    holdings: list[Holding]


class EquitySnapshot(Contract):
    """Recorded portfolio value at `taken_at`, from actual cash, holdings, and completed daily closes."""

    id: UUID
    portfolio_id: UUID
    taken_at: AwareDatetime
    cash: Decimal
    positions_value: Decimal
    equity: Decimal
    # External cash put in so far (today: the starting cash). Returns exclude it, so a deposit is not a gain.
    net_deposits: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    # Oldest close date used to value the holdings; null when the portfolio held only cash.
    prices_as_of: date | None
