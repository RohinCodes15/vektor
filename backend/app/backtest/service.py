"""Run, store, and retrieve backtests on real daily history from the market data service. Paper-only: nothing is
ever sent to a broker. Market data failures (MarketDataUnavailable, InvalidMarketData) propagate unchanged, so a
backtest never runs on missing or invalid prices.
"""

import logging
from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from app.backtest.engine import Costs, Holding, Simulation, simulate
from app.backtest.errors import BacktestNotFound, BacktestRejected
from app.backtest.metrics import Performance, compute_performance
from app.backtest.prices import Aligned, Bar, adjust, align
from app.backtest.store import BacktestStore
from app.backtest.strategies import signal_series, warmup_bars
from app.contracts import (
    Backtest,
    BacktestCreate,
    BacktestEquityPoint,
    BacktestMetrics,
    BacktestPosition,
    BacktestRejectedOrder,
    BacktestSettings,
    BacktestStrategy,
    BacktestSummary,
    BacktestTrade,
    MarketHistoryQuery,
)
from app.market_data.errors import MarketDataNotFound
from app.market_data.service import MarketDataService, utc_now
from app.portfolio.accounting import to_cents

logger = logging.getLogger("vektor.backtest")

BACKTEST_CURRENCY = "USD"
BASIS_POINTS = Decimal(10_000)


class BacktestService:
    def __init__(
        self, store: BacktestStore, market_data: MarketDataService, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self._store = store
        self._market_data = market_data
        self._clock = clock

    def run(self, request: BacktestCreate) -> Backtest:
        """Simulate the request on adjusted daily bars and store the result. Raises BacktestRejected on unusable data."""
        aligned = align({symbol: self._bars(symbol, request) for symbol in request.symbols})
        shortfall = _shortfall(request, request.strategy, aligned)
        if shortfall is not None:
            raise BacktestRejected(shortfall)
        simulation = _simulate(request, request.strategy, aligned)
        performance = _performance(request, simulation)
        backtest = _backtest(uuid4(), self._clock(), request, aligned, simulation, performance)
        self._store.add(backtest)
        logger.info(
            "backtest completed",
            extra={
                "backtest_id": str(backtest.id),
                "strategy": request.strategy.kind,
                "symbols": request.symbols,
                "bars": backtest.bars,
                "trades": backtest.metrics.trades,
            },
        )
        return backtest

    def get(self, backtest_id: UUID) -> Backtest:
        backtest = self._store.get(backtest_id)
        if backtest is None:
            raise BacktestNotFound(backtest_id)
        return backtest

    def list_backtests(self) -> list[BacktestSummary]:
        return self._store.list_summaries()

    def _bars(self, symbol: str, request: BacktestSettings) -> list[Bar]:
        query = MarketHistoryQuery(symbol=symbol, start=request.start, end=request.end)
        try:
            history = self._market_data.get_history(query)
        except MarketDataNotFound:
            raise BacktestRejected(
                f"No daily history for {symbol} between {request.start} and {request.end}. Check the symbol and dates."
            ) from None
        if history.currency != BACKTEST_CURRENCY:
            raise BacktestRejected(
                f"{symbol} is priced in {history.currency or 'an unreported currency'}; "
                f"backtests use {BACKTEST_CURRENCY} only."
            )
        bars = [adjust(bar) for bar in history.bars]
        if any(bar is None for bar in bars):
            raise BacktestRejected(f"{symbol} has adjusted prices below $0.0001, too small to simulate.")
        return [bar for bar in bars if bar is not None]


def _shortfall(request: BacktestSettings, strategy: BacktestStrategy, aligned: Aligned) -> str | None:
    """Why the range is too short for the strategy's warm-up, or None when it is long enough."""
    required = warmup_bars(strategy)
    if len(aligned.calendar) >= required:
        return None
    return (
        f"Not enough history: {strategy.kind} needs at least {required} trading days on which every "
        f"symbol has a bar between {request.start} and {request.end}; found {len(aligned.calendar)}."
    )


def _simulate(request: BacktestSettings, strategy: BacktestStrategy, aligned: Aligned) -> Simulation:
    signals = {symbol: signal_series(strategy, [bar.close for bar in bars]) for symbol, bars in aligned.bars.items()}
    costs = Costs(
        fee_per_trade=request.fee_per_trade,
        fee_rate=request.fee_bps / BASIS_POINTS,
        slippage=request.slippage_bps / BASIS_POINTS,
    )
    return simulate(
        aligned.calendar, aligned.bars, signals, request.starting_cash, costs, request.position_size_pct / 100
    )


def _performance(request: BacktestSettings, simulation: Simulation) -> Performance:
    return compute_performance(
        request.starting_cash,
        [point.equity for point in simulation.equity_curve],
        [fill.realized_pnl for fill in simulation.account.fills if fill.realized_pnl is not None],
    )


def _metrics(simulation: Simulation, performance: Performance) -> BacktestMetrics:
    fills = simulation.account.fills
    return BacktestMetrics(
        final_equity=simulation.equity_curve[-1].equity,
        total_return_pct=performance.total_return_pct,
        annualized_return_pct=performance.annualized_return_pct,
        volatility_pct=performance.volatility_pct,
        max_drawdown_pct=performance.max_drawdown_pct,
        sharpe_ratio=performance.sharpe_ratio,
        win_rate_pct=performance.win_rate_pct,
        trades=len(fills),
        closed_trades=performance.closed_trades,
        winning_trades=performance.winning_trades,
        total_fees=sum((fill.fee for fill in fills), Decimal("0.00")),
    )


def _backtest(
    backtest_id: UUID,
    created_at: datetime,
    request: BacktestCreate,
    aligned: Aligned,
    simulation: Simulation,
    performance: Performance,
) -> Backtest:
    account = simulation.account
    curve = simulation.equity_curve
    return Backtest(
        id=backtest_id,
        currency=BACKTEST_CURRENCY,
        config=request,
        created_at=created_at,
        source="yahoo_finance",
        bars=len(aligned.calendar),
        first_date=aligned.calendar[0],
        last_date=aligned.calendar[-1],
        metrics=_metrics(simulation, performance),
        warnings=list(performance.warnings),
        equity_curve=[
            BacktestEquityPoint(
                date=p.date, cash=p.cash, positions_value=p.positions_value, equity=p.equity, drawdown_pct=drawdown
            )
            for p, drawdown in zip(curve, performance.drawdowns_pct, strict=True)
        ],
        trades=[BacktestTrade(**asdict(fill)) for fill in account.fills],
        rejected_orders=[BacktestRejectedOrder(**asdict(rejection)) for rejection in account.rejections],
        open_positions=_open_positions(account.holdings, {s: bars[-1].close for s, bars in aligned.bars.items()}),
    )


def _open_positions(holdings: Mapping[str, Holding], closes: Mapping[str, Decimal]) -> list[BacktestPosition]:
    positions = []
    for symbol in sorted(holdings):
        holding = holdings[symbol]
        value = to_cents(holding.quantity * closes[symbol])
        positions.append(
            BacktestPosition(
                symbol=symbol,
                quantity=holding.quantity,
                cost_basis=holding.cost,
                last_price=closes[symbol],
                market_value=value,
                unrealized_pnl=value - holding.cost,
            )
        )
    return positions
