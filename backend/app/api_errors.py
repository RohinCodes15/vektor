"""Every API error is an ErrorResponse: {"detail": "<message>"}."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.contracts import ErrorResponse
from app.market_data.errors import MarketDataError
from app.portfolio.errors import PortfolioError
from app.validation import summarize_errors

logger = logging.getLogger("vektor")


def error_response(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=ErrorResponse(detail=detail).model_dump())


async def _request_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(422, summarize_errors(exc.errors()))


async def _domain_error(_: Request, exc: MarketDataError | PortfolioError) -> JSONResponse:
    return error_response(exc.status_code, exc.message)


async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled error", extra={"path": request.url.path}, exc_info=exc)
    return error_response(500, "Internal server error")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _request_validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(MarketDataError, _domain_error)  # type: ignore[arg-type]
    app.add_exception_handler(PortfolioError, _domain_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unexpected_error)
