"""Paper portfolio operations. Orders and valuations use real daily closes from the market data service.

Prices come from completed days only (the window ends yesterday, UTC): today's bar is still changing while markets
are open, and Yahoo can report it with missing values. Completed-day ranges are also served from the market data cache.
"""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from functools import partial
from uuid import UUID

from app.contracts import (
    MarketHistoryQuery,
    PaperOrder,
    Portfolio,
    PortfolioCreate,
    PortfolioHoldings,
    PortfolioUpdate,
    Transaction,
)
from app.market_data.errors import MarketDataNotFound
from app.market_data.service import MarketDataService, utc_now
from app.portfolio.accounting import Quote, Valuation, fill_order, to_price, value_portfolio
from app.portfolio.errors import DuplicateOrder, OrderRejected, PortfolioNotFound
from app.portfolio.store import PortfolioStore

logger = logging.getLogger("vektor.portfolio")

# How many completed days to search for the latest close; covers weekends and multi-day market holidays.
PRICE_LOOKBACK_DAYS = 14
PORTFOLIO_CURRENCY = "USD"


class PriceUnavailable(Exception):
    """No usable recent close for a symbol: unknown, delisted, halted, or not priced in USD."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class PortfolioService:
    def __init__(
        self, store: PortfolioStore, market_data: MarketDataService, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self._store = store
        self._market_data = market_data
        self._clock = clock

    def create(self, request: PortfolioCreate) -> Portfolio:
        portfolio = self._store.create(request.name, request.starting_cash, self._clock())
        logger.info("portfolio created", extra={"portfolio_id": str(portfolio.id)})
        return portfolio

    def list_portfolios(self) -> list[Portfolio]:
        return self._store.list_portfolios()

    def get(self, portfolio_id: UUID) -> Portfolio:
        portfolio = self._store.get(portfolio_id)
        if portfolio is None:
            raise PortfolioNotFound(portfolio_id)
        return portfolio

    def update(self, portfolio_id: UUID, request: PortfolioUpdate) -> Portfolio:
        portfolio = self._store.rename(portfolio_id, request.name, self._clock())
        if portfolio is None:
            raise PortfolioNotFound(portfolio_id)
        return portfolio

    def delete(self, portfolio_id: UUID) -> None:
        if not self._store.delete(portfolio_id):
            raise PortfolioNotFound(portfolio_id)
        logger.info("portfolio deleted", extra={"portfolio_id": str(portfolio_id)})

    def transactions(self, portfolio_id: UUID) -> list[Transaction]:
        self.get(portfolio_id)
        return self._store.transactions(portfolio_id)

    def submit_order(self, portfolio_id: UUID, order: PaperOrder) -> tuple[Transaction, bool]:
        """Execute a paper market order at the latest completed daily close. Returns (transaction, newly_executed).

        Resubmitting a client_order_id returns the original transaction without executing again.
        """
        self.get(portfolio_id)
        earlier = self._store.find_order(portfolio_id, order.client_order_id)
        if earlier is not None:  # replay without needing a market price
            return _replay(earlier, order), False
        try:
            quote = self._latest_quote(order.symbol)
        except PriceUnavailable as error:
            raise OrderRejected(f"{error.reason} The order was not executed.") from None
        fill = partial(fill_order, order.side, order.symbol, order.quantity, quote.price)
        result = self._store.execute_order(portfolio_id, order, quote, fill, self._clock())
        if result is None:  # deleted while the price was being fetched
            raise PortfolioNotFound(portfolio_id)
        transaction, executed = result
        if not executed:  # a concurrent request with the same client_order_id won the race
            return _replay(transaction, order), False
        logger.info(
            "paper order executed",
            extra={"portfolio_id": str(portfolio_id), "transaction_id": str(transaction.id), "symbol": order.symbol,
                   "side": order.side, "quantity": str(order.quantity), "price": str(quote.price)},
        )
        return transaction, True

    def holdings(self, portfolio_id: UUID) -> PortfolioHoldings:
        """Value every position at its latest completed close. Unpriced holdings are null, never guessed."""
        portfolio, valuation, _ = self._value(portfolio_id)
        return PortfolioHoldings(
            portfolio_id=portfolio.id,
            currency=portfolio.currency,
            cash=portfolio.cash,
            positions_value=valuation.positions_value,
            equity=valuation.equity,
            unrealized_pnl=valuation.unrealized_pnl,
            realized_pnl=portfolio.realized_pnl,
            cash_allocation_pct=valuation.cash_allocation_pct,
            valued_at=self._clock(),
            holdings=list(valuation.holdings),
        )

    def _value(self, portfolio_id: UUID) -> tuple[Portfolio, Valuation, dict[str, Quote | None]]:
        """Value one consistent read of cash and positions at the latest completed closes."""
        state = self._store.state(portfolio_id)
        if state is None:
            raise PortfolioNotFound(portfolio_id)
        portfolio, positions = state
        quotes = {position.symbol: self._quote_or_none(position.symbol) for position in positions}
        return portfolio, value_portfolio(portfolio.cash, positions, quotes), quotes

    def _quote_or_none(self, symbol: str) -> Quote | None:
        try:
            return self._latest_quote(symbol)
        except PriceUnavailable as error:
            logger.warning("holding has no market price", extra={"symbol": symbol, "reason": error.reason})
            return None

    def _latest_quote(self, symbol: str) -> Quote:
        """The most recent close among the PRICE_LOOKBACK_DAYS days before today (UTC).

        Raises PriceUnavailable when there is none or it is not in USD. Provider outages and invalid data
        (MarketDataUnavailable, InvalidMarketData) propagate unchanged, so nothing executes on bad data.
        """
        today = self._clock().date()
        query = MarketHistoryQuery(
            symbol=symbol, start=today - timedelta(days=PRICE_LOOKBACK_DAYS), end=today - timedelta(days=1)
        )
        try:
            history = self._market_data.get_history(query)
        except MarketDataNotFound:
            raise PriceUnavailable(
                f"No daily close for {symbol} in the {PRICE_LOOKBACK_DAYS} days before today. Check the symbol."
            ) from None
        if history.currency != PORTFOLIO_CURRENCY:
            raise PriceUnavailable(
                f"{symbol} is priced in {history.currency or 'an unreported currency'}; "
                f"portfolios hold {PORTFOLIO_CURRENCY} only."
            )
        bar = history.bars[-1]
        return Quote(price=to_price(bar.close), price_date=bar.date)


def _replay(earlier: Transaction, order: PaperOrder) -> Transaction:
    if (earlier.symbol, earlier.side, earlier.quantity) != (order.symbol, order.side, order.quantity):
        raise DuplicateOrder(order.client_order_id)
    return earlier
