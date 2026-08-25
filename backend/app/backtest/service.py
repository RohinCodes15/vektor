"""Run, store, and retrieve backtests on real daily history from the market data service. Paper-only: nothing is
ever sent to a broker. Market data failures (MarketDataUnavailable, InvalidMarketData) propagate unchanged, so a
backtest never runs on missing or invalid prices.
"""

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from app.backtest.comparison import differences, leaders
from app.backtest.engine import Costs, Holding, Simulation, simulate
from app.backtest.errors import BacktestNotFound, BacktestRejected
from app.backtest.metrics import Performance, compute_performance
from app.backtest.optimization import Scored, objective_value, overfitting_report, rank, split_calendar
from app.backtest.prices import Aligned, Bar, adjust, align
from app.backtest.store import BacktestStore
from app.backtest.strategies import signal_series, warmup_bars
from app.contracts import (
    Backtest,
    BacktestComparison,
    BacktestComparisonCreate,
    BacktestCreate,
    BacktestEquityPoint,
    BacktestMetrics,
    BacktestOptimization,
    BacktestOptimizationCreate,
    BacktestPosition,
    BacktestRejectedOrder,
    BacktestSettings,
    BacktestStrategy,
    BacktestSummary,
    BacktestTrade,
    MarketHistoryQuery,
    OptimizationCandidate,
    OptimizationSegment,
    OptimizationSelection,
    OptimizationSplit,
    StrategyComparisonResult,
)
from app.market_data.errors import MarketDataNotFound
from app.market_data.service import MarketDataService, utc_now
from app.portfolio.accounting import to_cents

logger = logging.getLogger("vektor.backtest")

BACKTEST_CURRENCY = "USD"
BASIS_POINTS = Decimal(10_000)
COMPARISON_DISCLAIMER = (
    "Paper simulation on past daily prices. A strategy that led in this comparison is not guaranteed, or even likely, "
    "to lead or return anything in the future. Not investment advice."
)
OPTIMIZATION_DISCLAIMER = (
    "Paper simulation on past daily prices. The best parameters on past data are not guaranteed, or even likely, "
    "to work in the future, and a good test result is one more historical sample, not a prediction. "
    "Not investment advice."
)
OPTIMIZATION_LIMITATIONS = (
    "Ranking uses only the training segment; the test segment is evaluated once, for the selected parameters.",
    (
        "Each segment is simulated on its own from the starting cash, so indicators warm up inside it and the test "
        "segment never sees training positions or signals."
    ),
    (
        "One train/test split of one symbol's history is a single sample: a different range or split can select "
        "different parameters."
    ),
    "Searching many combinations raises the chance that the winner fits noise (selection bias).",
    "Every backtest limitation applies: daily bars, fills at the next open, long only, whole shares.",
)


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

    def compare(self, request: BacktestComparisonCreate) -> BacktestComparison:
        """Backtest each strategy on the same adjusted bars. Nothing is stored. Raises BacktestRejected on unusable
        data; a strategy with too little history for its warm-up is reported as unavailable instead.
        """
        aligned = align({request.symbol: self._bars(request.symbol, request)})
        results = [_compared(request, strategy, aligned) for strategy in request.strategies]
        baseline = results[0].metrics
        if baseline is not None:
            results = [
                r.model_copy(update={"vs_baseline": differences(r.metrics, baseline)}) if r.metrics else r
                for r in results
            ]
        logger.info(
            "backtest comparison completed",
            extra={
                "symbol": request.symbol,
                "strategies": [strategy.kind for strategy in request.strategies],
                "bars": len(aligned.calendar),
            },
        )
        return BacktestComparison(
            currency=BACKTEST_CURRENCY,
            source="yahoo_finance",
            config=request,
            bars=len(aligned.calendar),
            first_date=aligned.calendar[0],
            last_date=aligned.calendar[-1],
            dates=list(aligned.calendar),
            results=results,
            leaders=leaders([r.metrics for r in results]),
            disclaimer=COMPARISON_DISCLAIMER,
        )

    def optimize(self, request: BacktestOptimizationCreate) -> BacktestOptimization:
        """Grid-search one strategy's parameters: rank on the training days, evaluate the winner on the later test
        days. Nothing is stored. Raises BacktestRejected on unusable data or when no candidate fits both segments.
        """
        aligned = align({request.symbol: self._bars(request.symbol, request)})
        split = split_calendar(aligned.calendar, request.train_pct)
        train, test = _slice(aligned, 0, len(split.train)), _slice(aligned, len(split.train), len(aligned.calendar))
        strategies: Sequence[BacktestStrategy] = request.grid.strategies()
        shortest = min(len(split.train), len(split.test))
        eligible = [(i, s) for i, s in enumerate(strategies) if warmup_bars(s) <= shortest]
        if not eligible:
            raise BacktestRejected(_optimization_shortfall(request, strategies, split.train, split.test))
        scored = [Scored(i, strategy, _segment_metrics(request, strategy, train)) for i, strategy in eligible]
        ranked = rank(scored, request.objective)
        selected = _selection(request, ranked[0], len(eligible), train, test) if ranked else None
        logger.info(
            "backtest optimization completed",
            extra={
                "symbol": request.symbol,
                "strategy": request.grid.kind,
                "objective": request.objective,
                "candidates": len(eligible),
                "bars": len(aligned.calendar),
            },
        )
        return BacktestOptimization(
            currency=BACKTEST_CURRENCY,
            source="yahoo_finance",
            config=request,
            bars=len(aligned.calendar),
            split=OptimizationSplit(
                train_pct=request.train_pct,
                train_bars=len(split.train),
                train_first_date=split.train[0],
                train_last_date=split.train[-1],
                test_bars=len(split.test),
                test_first_date=split.test[0],
                test_last_date=split.test[-1],
            ),
            better="higher",
            candidates_total=len(strategies),
            candidates_evaluated=len(eligible),
            candidates_skipped=len(strategies) - len(eligible),
            candidates_unranked=len(eligible) - len(ranked),
            ranked=[
                OptimizationCandidate(
                    rank=position,
                    strategy=s.strategy,
                    objective_value=_objective(s, request),
                    train_metrics=s.metrics,
                )
                for position, s in enumerate(ranked[: request.top_n], start=1)
            ],
            selected=selected,
            selection_reason=None if ranked else (
                f"No candidate has a defined {request.objective} on the training data, so none was selected."
            ),
            limitations=list(OPTIMIZATION_LIMITATIONS),
            disclaimer=OPTIMIZATION_DISCLAIMER,
        )

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


def _compared(
    request: BacktestComparisonCreate, strategy: BacktestStrategy, aligned: Aligned
) -> StrategyComparisonResult:
    shortfall = _shortfall(request, strategy, aligned)
    if shortfall is not None:
        return StrategyComparisonResult(
            strategy=strategy, status="unavailable", unavailable_reason=shortfall, metrics=None, warnings=[],
            equity=None, vs_baseline=None,
        )
    simulation = _simulate(request, strategy, aligned)
    performance = _performance(request, simulation)
    return StrategyComparisonResult(
        strategy=strategy,
        status="available",
        unavailable_reason=None,
        metrics=_metrics(simulation, performance),
        warnings=list(performance.warnings),
        equity=[point.equity for point in simulation.equity_curve],
        vs_baseline=None,
    )


def _slice(aligned: Aligned, start: int, stop: int) -> Aligned:
    return Aligned(aligned.calendar[start:stop], {symbol: bars[start:stop] for symbol, bars in aligned.bars.items()})


def _optimization_shortfall(
    request: BacktestOptimizationCreate,
    strategies: Sequence[BacktestStrategy],
    train: Sequence[date],
    test: Sequence[date],
) -> str:
    required = min(warmup_bars(strategy) for strategy in strategies)
    return (
        f"Not enough history to optimize: the candidate with the shortest warm-up needs {required} trading days in "
        f"both the training and the test segment, but the {request.train_pct}/{100 - request.train_pct} split of "
        f"{request.start} to {request.end} has {len(train)} training and {len(test)} test days. "
        "Widen the date range or search shorter windows."
    )


def _objective(scored: Scored, request: BacktestOptimizationCreate) -> Decimal:
    value = objective_value(scored.metrics, request.objective)
    if value is None:  # rank() returns only candidates with a defined objective
        raise ValueError("ranked candidate has no objective value")
    return value


def _selection(
    request: BacktestOptimizationCreate, best: Scored, candidates: int, train: Aligned, test: Aligned
) -> OptimizationSelection:
    train_segment = _segment(request, best.strategy, train)
    test_segment = _segment(request, best.strategy, test)
    return OptimizationSelection(
        strategy=best.strategy,
        train=train_segment,
        test=test_segment,
        overfitting=overfitting_report(
            best.strategy, request.grid, candidates, train_segment.metrics, test_segment.metrics
        ),
    )


def _segment_metrics(request: BacktestSettings, strategy: BacktestStrategy, aligned: Aligned) -> BacktestMetrics:
    simulation = _simulate(request, strategy, aligned)
    return _metrics(simulation, _performance(request, simulation))


def _segment(request: BacktestSettings, strategy: BacktestStrategy, aligned: Aligned) -> OptimizationSegment:
    simulation = _simulate(request, strategy, aligned)
    performance = _performance(request, simulation)
    return OptimizationSegment(
        first_date=aligned.calendar[0],
        last_date=aligned.calendar[-1],
        bars=len(aligned.calendar),
        metrics=_metrics(simulation, performance),
        warnings=list(performance.warnings),
        equity_curve=_equity_points(simulation, performance),
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
        equity_curve=_equity_points(simulation, performance),
        trades=[BacktestTrade(**asdict(fill)) for fill in account.fills],
        rejected_orders=[BacktestRejectedOrder(**asdict(rejection)) for rejection in account.rejections],
        open_positions=_open_positions(account.holdings, {s: bars[-1].close for s, bars in aligned.bars.items()}),
    )


def _equity_points(simulation: Simulation, performance: Performance) -> list[BacktestEquityPoint]:
    return [
        BacktestEquityPoint(
            date=p.date, cash=p.cash, positions_value=p.positions_value, equity=p.equity, drawdown_pct=drawdown
        )
        for p, drawdown in zip(simulation.equity_curve, performance.drawdowns_pct, strict=True)
    ]


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
