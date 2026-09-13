"""Portfolio failures. Messages are safe to show to API clients."""

from uuid import UUID


class PortfolioError(Exception):
    status_code = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class PortfolioNotFound(PortfolioError):
    status_code = 404

    def __init__(self, portfolio_id: UUID) -> None:
        super().__init__(f"Portfolio {portfolio_id} not found.")


class OrderRejected(PortfolioError):
    """The order cannot execute (no price, insufficient cash, overselling). Nothing was changed."""

    status_code = 422


class DuplicateOrder(PortfolioError):
    """The client_order_id was already used for a different order in this portfolio."""

    status_code = 409

    def __init__(self, client_order_id: str) -> None:
        super().__init__(
            f"client_order_id {client_order_id!r} was already used for a different order in this portfolio."
        )
