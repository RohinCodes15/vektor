from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from app.contracts import (
    EquitySnapshot,
    ErrorResponse,
    PaperOrder,
    Portfolio,
    PortfolioCreate,
    PortfolioHoldings,
    PortfolioUpdate,
    Transaction,
)
from app.portfolio.service import PortfolioService

router = APIRouter(prefix="/portfolios", tags=["paper portfolios"])

NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ErrorResponse, "description": "Portfolio not found"}}
INVALID: dict[int | str, dict[str, Any]] = {422: {"model": ErrorResponse, "description": "Invalid request"}}
MARKET_DATA: dict[int | str, dict[str, Any]] = {
    502: {"model": ErrorResponse, "description": "Market data provider returned invalid data"},
    503: {"model": ErrorResponse, "description": "Market data provider unreachable, timed out, or rate limited"},
}
ORDER_RESPONSES: dict[int | str, dict[str, Any]] = {
    **NOT_FOUND,
    **MARKET_DATA,
    200: {"model": Transaction, "description": "Replay: this client_order_id already executed; nothing changed"},
    409: {"model": ErrorResponse, "description": "client_order_id already used for a different order"},
    422: {
        "model": ErrorResponse,
        "description": "Invalid order, unknown symbol, no recent market price, insufficient cash, or overselling. "
        "Nothing was executed.",
    },
}

def get_portfolio_service(request: Request) -> PortfolioService:
    service: PortfolioService = request.app.state.portfolio_service
    return service


Service = Annotated[PortfolioService, Depends(get_portfolio_service)]


@router.post("", response_model=Portfolio, status_code=status.HTTP_201_CREATED, responses=INVALID)
def create_portfolio(body: PortfolioCreate, service: Service) -> Portfolio:
    """Create a paper portfolio funded with virtual USD cash."""
    return service.create(body)


@router.get("", response_model=list[Portfolio])
def list_portfolios(service: Service) -> list[Portfolio]:
    return service.list_portfolios()


@router.get("/{portfolio_id}", response_model=Portfolio, responses={**NOT_FOUND, **INVALID})
def get_portfolio(portfolio_id: UUID, service: Service) -> Portfolio:
    return service.get(portfolio_id)


@router.patch("/{portfolio_id}", response_model=Portfolio, responses={**NOT_FOUND, **INVALID})
def update_portfolio(portfolio_id: UUID, body: PortfolioUpdate, service: Service) -> Portfolio:
    """Rename a portfolio. Cash and holdings change only through orders."""
    return service.update(portfolio_id, body)


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT, responses={**NOT_FOUND, **INVALID})
def delete_portfolio(portfolio_id: UUID, service: Service) -> Response:
    """Permanently delete a portfolio with its holdings and transaction history."""
    service.delete(portfolio_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{portfolio_id}/holdings", response_model=PortfolioHoldings, responses={**NOT_FOUND, **INVALID, **MARKET_DATA}
)
def get_holdings(portfolio_id: UUID, service: Service) -> PortfolioHoldings:
    """Cash, positions, equity, P&L, and allocation, valued at each symbol's latest completed daily close."""
    return service.holdings(portfolio_id)


@router.post(
    "/{portfolio_id}/orders", response_model=Transaction, status_code=status.HTTP_201_CREATED, responses=ORDER_RESPONSES
)
def submit_order(portfolio_id: UUID, body: PaperOrder, response: Response, service: Service) -> Transaction:
    """Execute a simulated market order at the latest completed daily close. Paper only: nothing leaves this app."""
    transaction, executed = service.submit_order(portfolio_id, body)
    if not executed:
        response.status_code = status.HTTP_200_OK
    return transaction


@router.get("/{portfolio_id}/transactions", response_model=list[Transaction], responses={**NOT_FOUND, **INVALID})
def list_transactions(portfolio_id: UUID, service: Service) -> list[Transaction]:
    """Every executed order, oldest first."""
    return service.transactions(portfolio_id)


@router.post(
    "/{portfolio_id}/snapshots",
    response_model=EquitySnapshot,
    status_code=status.HTTP_201_CREATED,
    responses={
        **NOT_FOUND,
        **MARKET_DATA,
        422: {"model": ErrorResponse, "description": "Invalid id, or a holding has no recent price (nothing stored)"},
    },
)
def record_snapshot(portfolio_id: UUID, service: Service) -> EquitySnapshot:
    """Record the portfolio's equity now, valued at the latest completed daily closes. Never estimated."""
    return service.snapshot(portfolio_id)


@router.get("/{portfolio_id}/equity-history", response_model=list[EquitySnapshot], responses={**NOT_FOUND, **INVALID})
def equity_history(portfolio_id: UUID, service: Service) -> list[EquitySnapshot]:
    """Every recorded equity snapshot, oldest first. Only recorded values; nothing is backfilled."""
    return service.equity_history(portfolio_id)
