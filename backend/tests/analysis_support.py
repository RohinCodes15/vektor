"""Shared helpers for analysis tests: real backtests on fake market data, and a fake AI provider. No network."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from app.backtest.service import BacktestService
from app.backtest.store import BacktestStore
from app.contracts import AnalysisInsight, AnalysisInterpretation, Backtest, BacktestCreate, PriceBar
from app.market_data.cache import HistoryCache
from app.market_data.service import MarketDataService
from tests.fakes import FakeProvider

NOW = datetime(2024, 7, 1, 15, 0, tzinfo=UTC)
FIRST_DAY = date(2024, 1, 2)
# Rises, falls below its starting level, then recovers: an SMA(2/3) crossover buys, sells, and buys again.
SWING = [10, 10, 10, 11, 12, 13, 12, 11, 10, 9, 10, 11, 12, 13, 14]


def price_bars(closes: list[float]) -> list[PriceBar]:
    return [
        PriceBar(date=FIRST_DAY + timedelta(days=i), open=c, high=c + 1, low=c - 1, close=c, adjusted_close=c,
                 volume=1000)
        for i, c in enumerate(closes)
    ]


def backtest_service(tmp_path: Path, closes: list[float]) -> BacktestService:
    market = MarketDataService(FakeProvider(price_bars(closes)), HistoryCache(tmp_path / "cache.sqlite3"),
                               timedelta(hours=24), clock=lambda: NOW)
    return BacktestService(BacktestStore(tmp_path / "backtests.sqlite3"), market, clock=lambda: NOW)


COSTS = {"fee_per_trade": "1", "fee_bps": "5", "slippage_bps": "10"}
NO_COSTS = {"fee_per_trade": "0", "fee_bps": "0", "slippage_bps": "0"}


def run_backtest(
    tmp_path: Path, closes: list[float], strategy: dict[str, Any], costs: dict[str, str] = COSTS
) -> tuple[BacktestService, Backtest]:
    service = backtest_service(tmp_path, closes)
    request = BacktestCreate.model_validate({
        "symbols": ["AAPL"], "start": "2024-01-01", "end": "2024-06-28", "starting_cash": "10000",
        "strategy": strategy, **costs,
    })
    return service, service.run(request)


def interpretation(evidence: list[str] | None = None) -> AnalysisInterpretation:
    cited = evidence or ["total_return_pct"]
    insight = AnalysisInsight(text="The simulation measured a total return of 1.0000%.", evidence=cited)
    return AnalysisInterpretation(
        summary="A short simulated test whose results may not generalize.",
        strategy_behavior=[insight], strengths=[], weaknesses=[insight], risk_factors=[], limitations=[insight],
    )


class FakeAI:
    """Stands in for an AI provider: records each call and returns or raises what it was given."""

    name = "anthropic"
    model = "test-model"

    def __init__(self, result: AnalysisInterpretation | Exception | None = None) -> None:
        self.result = result if result is not None else interpretation()
        self.calls: list[tuple[str, str]] = []

    def interpret(self, system: str, payload: str) -> AnalysisInterpretation:
        self.calls.append((system, payload))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result
