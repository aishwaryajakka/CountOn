"""Stable error envelope; validation values and exception details are redacted."""

from fastapi import FastAPI, Request
from pydantic import BaseModel
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import (
    ResourceNotFoundError,
    InvalidIntegrationError,
    AuthenticationError,
    EvaluationNotFoundError,
    ExpectationNotFoundError,
    InvalidExpectationError,
    IdempotencyConflictError,
)
from app.core.observability import request_id


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


def error_response(status, code, message, headers=None):
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id.get(),
            }
        },
        headers=headers,
    )


async def domain_error(request: Request, error: Exception):
    if isinstance(error, ResourceNotFoundError):
        return error_response(
            404,
            error.code,
            error.message,
        )

    if isinstance(error, InvalidIntegrationError):
        return error_response(
            422,
            "INVALID_INTEGRATION",
            "Invalid provider/type combination or null required field",
        )

    if isinstance(error, AuthenticationError):
        return error_response(
            401,
            "UNAUTHORIZED",
            "Authentication required or token invalid",
            {"WWW-Authenticate": "Bearer"},
        )

    if isinstance(error, IdempotencyConflictError):
        return error_response(
            409,
            "IDEMPOTENCY_CONFLICT",
            "Idempotency key was already used with different evidence",
        )

    if isinstance(error, ExpectationNotFoundError):
        return error_response(
            404,
            "EXPECTATION_NOT_FOUND",
            "Expectation not found",
        )

    if isinstance(error, EvaluationNotFoundError):
        return error_response(
            404,
            "EVALUATION_NOT_FOUND",
            "Evaluation not found",
        )

    if isinstance(error, InvalidExpectationError):
        return error_response(
            422,
            "INVALID_EXPECTATION",
            str(error),
        )

    return error_response(
        500,
        "DATABASE_ERROR",
        "Database operation failed",
    )


async def validation_error(request: Request, error):
    return error_response(
        422,
        "VALIDATION_ERROR",
        "Request validation failed",
    )


async def http_error(request: Request, error):
    code = {
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
    }.get(error.status_code, "HTTP_ERROR")

    return error_response(
        error.status_code,
        code,
        code.replace("_", " ").capitalize(),
        error.headers,
    )


def register_exception_handlers(app: FastAPI):
    for error in (
        ResourceNotFoundError,
        InvalidIntegrationError,
        AuthenticationError,
        ExpectationNotFoundError,
        EvaluationNotFoundError,
        InvalidExpectationError,
        IdempotencyConflictError,
        SQLAlchemyError,
    ):
        app.add_exception_handler(error, domain_error)

    app.add_exception_handler(
        RequestValidationError,
        validation_error,
    )

    app.add_exception_handler(
        HTTPException,
        http_error,
    )