"""FastAPI application factory and ASGI entrypoint."""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from app import __version__
from app.api.errors import (
    APIError,
    api_error_handler,
    http_error_handler,
    unexpected_error_handler,
    validation_error_handler,
)
from app.api.routers import chat, documents, health, system
from app.application import RAGApplication
from app.config import settings
from app.observability.context import request_context
from app.observability.logging import setup_logger
from app.observability.metrics import (
    configure_metrics,
    start_metrics_server,
    stop_metrics_server,
)
from app.observability.tracing import (
    configure_tracing,
    shutdown_tracing,
)

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{8,64}$")


def create_app(
    application: RAGApplication | None = None,
    *,
    configure_runtime: bool = True,
) -> FastAPI:
    owned_application = application is None
    rag_application = application or RAGApplication(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if configure_runtime:
            setup_logger(
                log_level=rag_application.settings.log_level,
                log_file_path=rag_application.settings.log_file_path,
                rotation=rag_application.settings.log_rotation,
                retention=rag_application.settings.log_retention,
                service=rag_application.settings.service_name,
                environment=rag_application.settings.app_env,
                console_format=rag_application.settings.log_console_format,
                file_format=rag_application.settings.log_file_format,
            )
            configure_metrics(rag_application.settings.metrics_enabled)
            configure_tracing(
                rag_application.settings.tracing_enabled,
                service_name=rag_application.settings.service_name,
                environment=rag_application.settings.app_env,
                endpoint=rag_application.settings.otel_exporter_otlp_endpoint,
            )
        if not rag_application.initialized:
            await run_in_threadpool(rag_application.initialize)
        if configure_runtime:
            start_metrics_server(
                host=rag_application.settings.metrics_host,
                port=rag_application.settings.metrics_port,
            )
        app.state.rag_application = rag_application
        try:
            yield
        finally:
            if owned_application:
                await run_in_threadpool(rag_application.close)
            if configure_runtime:
                stop_metrics_server()
                shutdown_tracing()

    api = FastAPI(
        title="RAG Knowledge Base API",
        version=__version__,
        description="Document ingestion and source-grounded streaming answers.",
        lifespan=lifespan,
    )
    api.state.rag_application = rag_application
    api.add_middleware(
        CORSMiddleware,
        allow_origins=rag_application.settings.api_cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @api.middleware("http")
    async def request_identity(request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "").strip()
        request_id = (
            supplied if _REQUEST_ID_PATTERN.fullmatch(supplied) else uuid4().hex
        )
        request.state.request_id = request_id
        with request_context(request_id=request_id):
            response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    api.add_exception_handler(APIError, api_error_handler)
    api.add_exception_handler(RequestValidationError, validation_error_handler)
    api.add_exception_handler(HTTPException, http_error_handler)
    api.add_exception_handler(Exception, unexpected_error_handler)

    @api.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"service": "rag-api", "version": __version__, "docs": "/docs"}

    prefix = "/api/v1"
    api.include_router(health.router, prefix=prefix)
    api.include_router(system.router, prefix=prefix)
    api.include_router(documents.router, prefix=prefix)
    api.include_router(chat.router, prefix=prefix)
    return api


app = create_app()
