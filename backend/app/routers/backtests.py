from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from app.backtest.service import BacktestService
from app.contracts import Backtest, BacktestCreate, BacktestSummary, ErrorResponse

router = APIRouter(prefix="/backtests", tags=["backtests"])

NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ErrorResponse, "description": "Backtest not found"}}
INVALID: dict[int | str, dict[str, Any]] = {422: {"model": ErrorResponse, "description": "Invalid id"}}
RUN_RESPONSES: dict[int | str, dict[str, Any]] = {
    422: {
        "model": ErrorResponse,
        "description": "Invalid request, unknown symbol, non-USD prices, or too little history for the strategy. "
        "Nothing was stored.",
    },
    502: {"model": ErrorResponse, "description": "Market data provider returned invalid data"},
    503: {"model": ErrorResponse, "description": "Market data provider unreachable, timed out, or rate limited"},
}


def get_backtest_service(request: Request) -> BacktestService:
    service: BacktestService = request.app.state.backtest_service
    return service


Service = Annotated[BacktestService, Depends(get_backtest_service)]


@router.post("", response_model=Backtest, status_code=status.HTTP_201_CREATED, responses=RUN_RESPONSES)
def run_backtest(body: BacktestCreate, service: Service) -> Backtest:
    """Run a paper-only backtest on completed daily history and store the result."""
    return service.run(body)


@router.get("", response_model=list[BacktestSummary])
def list_backtests(service: Service) -> list[BacktestSummary]:
    return service.list_backtests()


@router.get("/{backtest_id}", response_model=Backtest, responses={**NOT_FOUND, **INVALID})
def get_backtest(backtest_id: UUID, service: Service) -> Backtest:
    return service.get(backtest_id)
