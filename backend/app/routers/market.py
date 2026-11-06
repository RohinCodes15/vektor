from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request

from app.contracts import ErrorResponse, MarketHistoryQuery, MarketHistoryResponse
from app.market_data.service import MarketDataService

router = APIRouter(prefix="/market", tags=["market data"])

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "No bars for the symbol and range"},
    422: {"model": ErrorResponse, "description": "Invalid symbol, dates, or interval"},
    502: {"model": ErrorResponse, "description": "Provider returned invalid data (rejected, never repaired)"},
    503: {"model": ErrorResponse, "description": "Provider unreachable, timed out, or rate limited"},
}


def get_market_data_service(request: Request) -> MarketDataService:
    service: MarketDataService = request.app.state.market_data_service
    return service


@router.get("/history", response_model=MarketHistoryResponse, responses=ERROR_RESPONSES)
def market_history(
    query: Annotated[MarketHistoryQuery, Query()],
    service: Annotated[MarketDataService, Depends(get_market_data_service)],
) -> MarketHistoryResponse:
    """Read-only daily OHLCV bars from Yahoo Finance for an inclusive date range, cached locally."""
    return service.get_history(query)
