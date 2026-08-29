"""FastAPI dependencies for application-owned services."""

from __future__ import annotations

from fastapi import Request

from app.api.errors import APIError
from app.application import RAGApplication
from app.services.document_service import DocumentService
from app.services.rag_service import RAGService
from app.services.retrieval_service import RetrievalService


def get_application(request: Request) -> RAGApplication:
    return request.app.state.rag_application


def get_rag_service(request: Request) -> RAGService:
    application = get_application(request)
    if not application.initialized or application.rag_service is None:
        raise APIError(503, "application_unavailable", "RAG 服务尚未就绪。")
    return application.rag_service


def get_document_service(request: Request) -> DocumentService:
    application = get_application(request)
    if not application.initialized or application.document_service is None:
        raise APIError(503, "application_unavailable", "文档服务尚未就绪。")
    return application.document_service


def get_retrieval_service(request: Request) -> RetrievalService:
    application = get_application(request)
    if not application.initialized or application.retrieval_service is None:
        raise APIError(503, "retrieval_service_unavailable", "检索服务尚未就绪。")
    return application.retrieval_service
