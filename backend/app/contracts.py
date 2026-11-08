"""Shared API contracts (v1). Coordinated with frontend/ — see AGENTS.md before changing.

Simulation models are contracts only; no endpoints serve them yet. Backtest models back /api/v1/backtests;
comparison models back POST /api/v1/backtests/comparisons (Phase 3B.1).
Analysis models back POST /api/v1/backtests/{id}/analysis (Phase 3A.1, educational AI explanations of a backtest).
Market history models back the read-only GET /api/v1/market/history endpoint.
Portfolio models back the paper portfolio endpoints under /api/v1/portfolios; equity snapshots, analytics, allocation
and risk live under the same prefix. Money is a Decimal, serialized as a JSON string: cash, cost and P&L have 2 decimal
places, prices 4, percentages 2 (see app/portfolio/accounting.py); analytics, allocation and risk metrics have 4.
"""

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from itertools import pairwise
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
        if any(earlier >= later for earlier, later in pairwise(dates)):
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


class PortfolioAnalytics(Contract):
    """Metrics from recorded equity snapshots only. A metric is null when there is too little history for it.

    Percentages have 4 decimal places; see backend/README.md for every formula and assumption.
    """

    portfolio_id: UUID
    currency: PortfolioCurrency
    # taken_at of the latest snapshot; every value below is as of that moment.
    as_of: AwareDatetime | None
    snapshots: int
    # Days with at least one snapshot (the last snapshot of each UTC day is used).
    daily_observations: int
    equity: Decimal | None
    net_deposits: Decimal | None
    realized_pnl: Decimal | None
    unrealized_pnl: Decimal | None
    total_return_pct: Decimal | None
    latest_daily_return_pct: Decimal | None
    # Annualized: sample standard deviation of daily returns * sqrt(252).
    volatility_pct: Decimal | None
    # Largest peak-to-trough fall of the deposit-adjusted equity index; zero or negative.
    max_drawdown_pct: Decimal | None
    # Annualized, risk-free rate 0: mean daily return / standard deviation * sqrt(252).
    sharpe_ratio: Decimal | None


# Allocation and risk (Phase 2F.1). Computed now from actual holdings and completed daily closes; never estimated.
MetricStatus = Literal["available", "unavailable"]


class AssetAllocation(Contract):
    """One held asset. Value and weights are null when the holding has no recent price."""

    symbol: str
    quantity: Decimal
    last_price: Decimal | None
    price_date: date | None
    market_value: Decimal | None
    # Share of equity (cash + positions).
    weight_pct: Decimal | None
    # Share of the positions value (cash excluded).
    position_weight_pct: Decimal | None
    # True when price_date is more than 4 calendar days before today (UTC).
    stale: bool


class PortfolioAllocation(Contract):
    """Current allocation and concentration. Percentages and the HHI have 4 decimal places.

    `status` is "unavailable" when a holding has no recent price (every weight is then null), when there are no
    positions, or when equity is zero; `unavailable_reason` says which. See backend/README.md for the formulas.
    """

    portfolio_id: UUID
    currency: PortfolioCurrency
    valued_at: AwareDatetime
    status: MetricStatus
    unavailable_reason: str | None
    cash: Decimal
    positions_value: Decimal | None
    equity: Decimal | None
    cash_weight_pct: Decimal | None
    # Oldest price date used; null for a cash-only portfolio or when no holding is priced.
    prices_as_of: date | None
    unpriced_symbols: list[str]
    stale_symbols: list[str]
    assets: list[AssetAllocation]
    top_holding_symbol: str | None
    # Largest position_weight_pct.
    top_holding_pct: Decimal | None
    # Herfindahl-Hirschman index of position weights (fractions, cash excluded): 1/N to 1.
    hhi: Decimal | None


class AssetRisk(Contract):
    symbol: str
    weight_pct: Decimal
    # Annualized volatility of the asset's own daily returns.
    volatility_pct: Decimal
    # Annualized volatility points this asset adds to the portfolio; they sum to portfolio_volatility_pct.
    volatility_contribution_pct: Decimal | None
    # Share of portfolio volatility; the shares sum to 100. Null when portfolio volatility is zero.
    contribution_share_pct: Decimal | None


class AssetCorrelation(Contract):
    symbol_a: str
    symbol_b: str
    # Pearson correlation of aligned daily returns; null when either series is constant.
    correlation: Decimal | None


class PortfolioRisk(Contract):
    """Volatility contribution and correlation from aligned daily returns of the current holdings.

    Metrics are present only when `status` is "available": every holding is priced and has at least
    `min_observations` aligned daily returns ending within 4 days of today. Otherwise `unavailable_reason` says why.
    """

    portfolio_id: UUID
    currency: PortfolioCurrency
    valued_at: AwareDatetime
    status: MetricStatus
    unavailable_reason: str | None
    # Requested history window (inclusive) and the aligned returns found in it.
    window_start: date
    window_end: date
    observations: int
    min_observations: int
    # Last aligned close date; null when no date is shared by every holding.
    returns_as_of: date | None
    portfolio_volatility_pct: Decimal | None
    assets: list[AssetRisk]
    correlations: list[AssetCorrelation]


# Backtests (Phase 2G.1). Simulated on completed daily history only; nothing here reaches a broker.
class BuyAndHoldStrategy(Contract):
    """Buy every symbol once, on the first possible bar, and hold to the end."""

    kind: Literal["buy_and_hold"]


class SmaCrossoverStrategy(Contract):
    """Buy when the fast simple moving average of closes crosses above the slow one; sell when it crosses below."""

    kind: Literal["sma_crossover"]
    fast_window: int = Field(default=20, ge=2, le=250)
    slow_window: int = Field(default=50, ge=3, le=500)

    @model_validator(mode="after")
    def check_windows(self) -> Self:
        if self.fast_window >= self.slow_window:
            raise ValueError("fast_window must be smaller than slow_window")
        return self


class RsiStrategy(Contract):
    """Wilder's RSI of closes: buy when it is below `oversold`, sell when it is above `overbought`."""

    kind: Literal["rsi"]
    period: int = Field(default=14, ge=2, le=100)
    oversold: Decimal = Field(default=Decimal(30), gt=0, lt=100, max_digits=4, decimal_places=2)
    overbought: Decimal = Field(default=Decimal(70), gt=0, lt=100, max_digits=4, decimal_places=2)

    @model_validator(mode="after")
    def check_thresholds(self) -> Self:
        if self.oversold >= self.overbought:
            raise ValueError("oversold must be below overbought")
        return self


BacktestStrategy = Annotated[BuyAndHoldStrategy | SmaCrossoverStrategy | RsiStrategy, Field(discriminator="kind")]
# Basis points (1 bp = 0.01%) of the traded value, capped at 10%.
BasisPoints = Annotated[Decimal, Field(ge=0, le=1000, max_digits=6, decimal_places=2)]


def _tradable(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if not _TRADABLE_SYMBOL.fullmatch(symbol):
        raise ValueError("each symbol must be a ticker of 1-15 letters, digits, '.' or '-'")
    return symbol


class BacktestSettings(Contract):
    """Range, cash, sizing and costs shared by a backtest and a strategy comparison.

    `start` and `end` are inclusive calendar dates before today (UTC). Long-only and whole shares.
    """

    start: date
    end: date
    starting_cash: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    position_size_pct: Decimal = Field(default=Decimal(100), gt=0, le=100, max_digits=5, decimal_places=2)
    # Fixed commission per fill, in dollars.
    fee_per_trade: Decimal = Field(default=Decimal("0.00"), ge=0, le=1000, max_digits=6, decimal_places=2)
    # Commission proportional to each fill's notional.
    fee_bps: BasisPoints = Decimal(0)
    # Price moved against every fill: buys pay more, sells receive less.
    slippage_bps: BasisPoints = Decimal(0)

    @field_validator("starting_cash", "fee_per_trade")
    @classmethod
    def to_cents(cls, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"))  # exact: at most 2 decimal places were accepted

    @field_validator("position_size_pct", "fee_bps", "slippage_bps")
    @classmethod
    def canonical_number(cls, value: Decimal) -> Decimal:
        return _canonical(value)

    @model_validator(mode="after")
    def check_date_range(self) -> Self:
        if self.start >= self.end:
            raise ValueError("start must be before end")
        if self.end >= datetime.now(UTC).date():
            raise ValueError("end must be before today (UTC): only completed daily bars are simulated")
        return self


class BacktestCreate(BacktestSettings):
    """A backtest over completed daily bars. Each entry targets `position_size_pct` of equity split equally across
    `symbols`.
    """

    symbols: list[str] = Field(min_length=1, max_length=10)
    strategy: BacktestStrategy

    @field_validator("symbols", mode="before")
    @classmethod
    def normalize_symbols(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        # Non-strings are left for the list[str] check, which rejects them; they may not even be hashable.
        symbols = [_tradable(item) if isinstance(item, str) else item for item in value]
        tickers = [symbol for symbol in symbols if isinstance(symbol, str)]
        if len(set(tickers)) != len(tickers):
            raise ValueError("symbols must not repeat")
        return symbols


class BacktestComparisonCreate(BacktestSettings):
    """2 to 5 distinct strategies backtested on one symbol with the same range, cash, sizing, fees and slippage.

    The first strategy is the baseline that `StrategyComparisonResult.vs_baseline` is measured against.
    """

    symbol: str
    strategies: list[BacktestStrategy] = Field(min_length=2, max_length=5)

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: object) -> object:
        return _tradable(value) if isinstance(value, str) else value

    @field_validator("strategies")
    @classmethod
    def distinct_strategies(cls, value: list[BacktestStrategy]) -> list[BacktestStrategy]:
        if len(set(value)) != len(value):
            raise ValueError("strategies must not repeat: each needs a different kind or different parameters")
        return value


class BacktestTrade(Contract):
    """One simulated fill at the open of `fill_date`, from a signal at the close of `signal_date`.

    Prices are split- and dividend-adjusted (see backend/README.md). `notional` is quantity * price in cents.
    """

    symbol: str
    side: OrderSide
    signal_date: date
    fill_date: date
    quantity: int
    price: Decimal
    notional: Decimal
    fee: Decimal
    # Sells only: notional - fee - the position's cost (buy notional + buy fee).
    realized_pnl: Decimal | None


class BacktestRejectedOrder(Contract):
    """An order the simulation could not fill; nothing changed."""

    symbol: str
    side: OrderSide
    signal_date: date
    fill_date: date
    reason: str


class BacktestEquityPoint(Contract):
    """Account value at the close of `date`."""

    date: date
    cash: Decimal
    positions_value: Decimal
    equity: Decimal
    # Fall from the highest equity so far; zero or negative, 4 decimal places.
    drawdown_pct: Decimal


class BacktestPosition(Contract):
    """A position still open after the last bar, marked at its last adjusted close."""

    symbol: str
    quantity: int
    cost_basis: Decimal
    last_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal


class BacktestMetrics(Contract):
    """Performance of the equity curve. A metric is null when it is undefined; `Backtest.warnings` says why.

    Percentages and the Sharpe ratio have 4 decimal places; see backend/README.md for every formula.
    """

    final_equity: Decimal
    total_return_pct: Decimal
    annualized_return_pct: Decimal | None
    # Annualized: sample standard deviation of daily returns * sqrt(252).
    volatility_pct: Decimal | None
    max_drawdown_pct: Decimal
    # Annualized, risk-free rate 0: mean daily return / standard deviation * sqrt(252).
    sharpe_ratio: Decimal | None
    # Share of closed trades (sells) with a positive realized P&L.
    win_rate_pct: Decimal | None
    trades: int
    closed_trades: int
    winning_trades: int
    total_fees: Decimal


class Backtest(Contract):
    """A completed, deterministic backtest: the same request on the same data gives the same result."""

    id: UUID
    mode: TradingMode = "paper"
    currency: PortfolioCurrency
    config: BacktestCreate
    created_at: AwareDatetime
    source: MarketDataSource
    # Trading days simulated: the dates in the range on which every symbol has a bar.
    bars: int
    first_date: date
    last_date: date
    metrics: BacktestMetrics
    warnings: list[str]
    equity_curve: list[BacktestEquityPoint]
    trades: list[BacktestTrade]
    rejected_orders: list[BacktestRejectedOrder]
    open_positions: list[BacktestPosition]


class BacktestSummary(Contract):
    """A stored backtest without its equity curve and trade list."""

    id: UUID
    created_at: AwareDatetime
    config: BacktestCreate
    bars: int
    first_date: date
    last_date: date
    metrics: BacktestMetrics


# Strategy comparison (Phase 3B.1). Computed on request from real history, never stored; nothing reaches a broker.
ComparisonMetric = Literal[
    "total_return_pct", "annualized_return_pct", "volatility_pct", "sharpe_ratio", "max_drawdown_pct", "win_rate_pct"
]


class MetricDifferences(Contract):
    """This strategy's metric minus the baseline's: percentage points, or Sharpe units. Null when either is null."""

    total_return_pct: Decimal | None
    annualized_return_pct: Decimal | None
    volatility_pct: Decimal | None
    sharpe_ratio: Decimal | None
    max_drawdown_pct: Decimal | None
    win_rate_pct: Decimal | None


class StrategyComparisonResult(Contract):
    """One strategy's backtest. "unavailable" (with a reason, and metrics, equity and differences null) when the
    range has too few trading days for the strategy's warm-up.
    """

    strategy: BacktestStrategy
    status: MetricStatus
    unavailable_reason: str | None
    metrics: BacktestMetrics | None
    warnings: list[str]
    # Equity at each close, aligned one to one with `BacktestComparison.dates`.
    equity: list[Decimal] | None
    # Null for an unavailable strategy or when the baseline (the first strategy) is unavailable.
    vs_baseline: MetricDifferences | None


class MetricLeader(Contract):
    """The strategies (indices into `results`) with the best value of `metric`, ties included.

    `leaders` is empty, with a `reason`, when fewer than 2 strategies have the metric or all of them are equal.
    """

    metric: ComparisonMetric
    better: Literal["higher", "lower"]
    leaders: list[int]
    reason: str | None


class BacktestComparison(Contract):
    """Deterministic: the same request on the same data gives the same result. Describes the past only."""

    mode: TradingMode = "paper"
    currency: PortfolioCurrency
    source: MarketDataSource
    config: BacktestComparisonCreate
    # Trading days in the range, shared by every strategy.
    bars: int
    first_date: date
    last_date: date
    dates: list[date]
    results: list[StrategyComparisonResult]  # same order as config.strategies
    leaders: list[MetricLeader]
    disclaimer: str


# AI strategy analysis (Phase 3A.1). Educational and paper-only: explains a stored backtest and never gives advice.
AnalysisProviderName = Literal["anthropic"]


class AnalysisFact(Contract):
    """A value Vektor measured from the stored backtest. Facts are computed locally, never by the AI provider."""

    id: str
    label: str
    value: str


class AnalysisInsight(Contract):
    """One AI interpretation. `evidence` lists the ids of the measured facts it is based on."""

    text: str = Field(min_length=1, max_length=600)
    evidence: list[str] = Field(min_length=1, max_length=6)


class AnalysisInterpretation(Contract):
    """The AI provider's reading of the measured facts: interpretation, not measurement, and never advice."""

    summary: str = Field(min_length=1, max_length=800)
    strategy_behavior: list[AnalysisInsight] = Field(min_length=1, max_length=5)
    strengths: list[AnalysisInsight] = Field(max_length=5)
    weaknesses: list[AnalysisInsight] = Field(max_length=5)
    risk_factors: list[AnalysisInsight] = Field(max_length=5)
    limitations: list[AnalysisInsight] = Field(min_length=1, max_length=5)


class BacktestAnalysis(Contract):
    """Measured facts about a stored backtest plus, when an AI provider is configured, its interpretation.

    `status` is "unavailable" (with `unavailable_reason`, and `interpretation`, `provider` and `model` null) when no
    provider is configured. `facts` are always present and exact; nothing in them comes from the AI provider.
    """

    backtest_id: UUID
    mode: TradingMode = "paper"
    status: MetricStatus
    unavailable_reason: str | None
    generated_at: AwareDatetime
    provider: AnalysisProviderName | None
    model: str | None
    facts: list[AnalysisFact]
    interpretation: AnalysisInterpretation | None
    disclaimer: str
