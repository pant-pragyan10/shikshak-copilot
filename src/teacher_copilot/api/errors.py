"""Consistent error handling for the API.

Every failure returns the same envelope — ``{"error": {"type", "message"}}`` — and
never leaks internals, stack traces, or provider keys. Provider free-tier exhaustion
becomes a friendly 503 the frontend can show verbatim.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from teacher_copilot.providers.errors import (
    ProviderExhaustedError,
    ProviderModelNotFoundError,
)

logger = logging.getLogger("teacher_copilot.api")

_BUSY_MESSAGE = (
    "The system is busy right now (we run on free-tier AI limits). "
    "Please try again in a moment."
)
_GENERIC_MESSAGE = "Something went wrong. Please try again."


def _error(status_code: int, error_type: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"error": {"type": error_type, "message": message}}
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the API's exception handlers to ``app``."""

    @app.exception_handler(ProviderExhaustedError)
    async def _exhausted(request: Request, exc: ProviderExhaustedError) -> JSONResponse:
        logger.warning("providers exhausted: %s", exc.failures)
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "provider_exhausted", _BUSY_MESSAGE)

    @app.exception_handler(ProviderModelNotFoundError)
    async def _model_missing(request: Request, exc: ProviderModelNotFoundError) -> JSONResponse:
        # Operator-facing detail in the log; the user just sees "busy".
        logger.error("model not found (check deprecations / env): %s", exc)
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "provider_unavailable", _BUSY_MESSAGE)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Reshape FastAPI/Starlette HTTPExceptions into our consistent envelope.
        return _error(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _request_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "validation_error", str(exc.errors()))

    @app.exception_handler(ValidationError)
    async def _domain_validation(request: Request, exc: ValidationError) -> JSONResponse:
        # Raised when we build a domain model from user input (e.g. GradingRequest).
        return _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "validation_error", str(exc.errors()))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled API error")
        return _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", _GENERIC_MESSAGE)
