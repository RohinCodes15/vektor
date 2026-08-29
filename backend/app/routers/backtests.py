from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from app.analysis.service import AnalysisService
from app.backtest.service import BacktestService
from app.contracts import (
    Backtest,
    BacktestAnalysis,
    BacktestComparison,
    BacktestComparisonCreate,
    BacktestCreate,
    BacktestOptimization,
    BacktestOptimizationCreate,
    BacktestSummary,
    ErrorResponse,
)

router = APIRouter(prefix="/backtests", tags=["backtests"])

NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ErrorResponse, "description": "Backtest not found"}}
INVALID: dict[int | str, dict[str, Any]] = {422: {"model": ErrorResponse, "description": "Invalid id"}}
# Every POST under /backtests is an expensive request: rate limited and capped in concurrency (app/middleware.py).
LIMIT_RESPONSES: dict[int | str, dict[str, Any]] = {
    413: {"model": ErrorResponse, "description": "Request body larger than the configured limit"},
    429: {"model": ErrorResponse, "description": "Too many requests from this client; see the Retry-After header"},
}
RUN_RESPONSES: dict[int | str, dict[str, Any]] = {
    **LIMIT_RESPONSES,
    422: {
        "model": ErrorResponse,
        "description": "Invalid request, date range over the configured limit, unknown symbol, non-USD prices, or too "
        "little history for the strategy. Nothing was stored.",
    },
    502: {"model": ErrorResponse, "description": "Market data provider returned invalid data"},
    503: {
        "model": ErrorResponse,
        "description": "Market data provider unreachable, timed out, or rate limited, or the server is busy with other "
        "backtests (see Retry-After)",
    },
}
COMPARE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **RUN_RESPONSES,
    422: {
        "model": ErrorResponse,
        "description": "Invalid request, date range over the configured limit, unknown symbol, or non-USD prices. A "
        "strategy with too little history is reported as unavailable instead.",
    },
}
OPTIMIZE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **RUN_RESPONSES,
    422: {
        "model": ErrorResponse,
        "description": "Invalid request or grid (no valid or too many combinations), date range over the configured "
        "limit, unknown symbol, non-USD prices, or too little history for any candidate in both the training and the "
        "test segment.",
    },
}
ANALYSIS_RESPONSES: dict[int | str, dict[str, Any]] = {
    **NOT_FOUND,
    **INVALID,
    **LIMIT_RESPONSES,
    502: {"model": ErrorResponse, "description": "AI provider rejected the request or returned an invalid analysis"},
    503: {
        "model": ErrorResponse,
        "description": "AI provider timed out, rate limited, unreachable, or unauthorized, or the server is busy with "
        "other backtests (see Retry-After)",
    },
}


def get_backtest_service(request: Request) -> BacktestService:
    service: BacktestService = request.app.state.backtest_service
    return service


Service = Annotated[BacktestService, Depends(get_backtest_service)]


def get_analysis_service(request: Request) -> AnalysisService:
    service: AnalysisService = request.app.state.analysis_service
    return service


@router.post("", response_model=Backtest, status_code=status.HTTP_201_CREATED, responses=RUN_RESPONSES)
def run_backtest(body: BacktestCreate, service: Service) -> Backtest:
    """Run a paper-only backtest on completed daily history and store the result."""
    return service.run(body)


@router.post("/comparisons", response_model=BacktestComparison, responses=COMPARE_RESPONSES)
def compare_strategies(body: BacktestComparisonCreate, service: Service) -> BacktestComparison:
    """Backtest 2 to 5 strategies on the same symbol, range, cash and costs and compare them. Nothing is stored."""
    return service.compare(body)


@router.post("/optimizations", response_model=BacktestOptimization, responses=OPTIMIZE_RESPONSES)
def optimize_strategy(body: BacktestOptimizationCreate, service: Service) -> BacktestOptimization:
    """Grid-search a strategy's parameters with a chronological train/test split. Nothing is stored."""
    return service.optimize(body)


@router.get("", response_model=list[BacktestSummary])
def list_backtests(service: Service) -> list[BacktestSummary]:
    return service.list_backtests()


@router.get("/{backtest_id}", response_model=Backtest, responses={**NOT_FOUND, **INVALID})
def get_backtest(backtest_id: UUID, service: Service) -> Backtest:
    return service.get(backtest_id)


@router.post("/{backtest_id}/analysis", response_model=BacktestAnalysis, responses=ANALYSIS_RESPONSES)
def analyze_backtest(
    backtest_id: UUID, service: Annotated[AnalysisService, Depends(get_analysis_service)]
) -> BacktestAnalysis:
    """Educational explanation of a stored backtest: measured facts, plus an AI interpretation when configured."""
    return service.analyze(backtest_id)
