"""Central HTTP error mappings for framework-independent services."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import EvaluationNotFoundError, ExpectationNotFoundError, InvalidExpectationError

logger = logging.getLogger(__name__)


async def not_found_handler(request: Request, error: Exception) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(error)})


async def invalid_expectation_handler(request: Request, error: Exception) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(error)})


async def database_error_handler(request: Request, error: Exception) -> JSONResponse:
    # Do not log SQL parameters or leak integration payloads through tracebacks.
    logger.error("Database operation failed error_type=%s", type(error).__name__)
    return JSONResponse(status_code=500, content={"detail": "Database operation failed"})


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ExpectationNotFoundError, not_found_handler)
    app.add_exception_handler(EvaluationNotFoundError, not_found_handler)
    app.add_exception_handler(InvalidExpectationError, invalid_expectation_handler)
    app.add_exception_handler(SQLAlchemyError, database_error_handler)
