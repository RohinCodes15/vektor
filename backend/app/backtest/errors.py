"""Backtest failures. Messages are safe to show to API clients."""

from uuid import UUID


class BacktestError(Exception):
    status_code = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class BacktestNotFound(BacktestError):
    status_code = 404

    def __init__(self, backtest_id: UUID) -> None:
        super().__init__(f"Backtest {backtest_id} not found")


class BacktestRejected(BacktestError):
    """The backtest cannot run: unknown symbol, non-USD prices, or too few bars for the strategy. Nothing is stored."""

    status_code = 422
