"""Stable public error responses for the HTTP API."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.observability.logging import get_logger

logger = get_logger(__name__)


def _remember_retrieval_error(request: Request, code: str) -> None:
    if request.url.path == "/api/v1/retrieve":
        request.state.retrieval_error_code = code


class APIError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message


def _payload(
    request: Request,
    *,
    code: str,
    message: str,
    fields: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": getattr(request.state, "request_id", None),
    }
    if fields:
        body["fields"] = fields
    return {"error": body}


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    _remember_retrieval_error(request, exc.code)
    return JSONResponse(
        status_code=exc.status_code,
        content=_payload(request, code=exc.code, message=exc.message),
    )


async def validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    _remember_retrieval_error(request, "validation_error")
    fields = [
        {
            "field": ".".join(str(item) for item in error.get("loc", ())[1:]),
            "message": str(error.get("msg", "Invalid value")),
            "type": str(error.get("type", "validation_error")),
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=_payload(
            request,
            code="validation_error",
            message="请求参数不符合接口约束。",
            fields=fields,
        ),
    )


async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code = "not_found" if exc.status_code == 404 else "http_error"
    message = str(exc.detail) if isinstance(exc.detail, str) else "请求无法处理。"
    _remember_retrieval_error(request, code)
    return JSONResponse(
        status_code=exc.status_code,
        content=_payload(request, code=code, message=message),
        headers=exc.headers,
    )


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    _remember_retrieval_error(request, "internal_error")
    logger.exception(
        "未处理的 API 异常",
        event="api_request_failed",
        operation="http.request",
        status="error",
        error_type=type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content=_payload(
            request,
            code="internal_error",
            message="服务暂时无法处理请求。",
        ),
    )
