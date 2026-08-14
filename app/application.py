"""Composition root for the RAG application."""

from __future__ import annotations

from threading import RLock
from typing import Any

from app.config import Settings, settings
from app.core.document_chunker import DocumentChunker
from app.core.document_loader import UniversalDocumentLoader
from app.core.embedding_client import UniversalEmbeddingClient
from app.core.generator import RAGGenerator, UniversalLLMClient
from app.core.retriever import Retriever
from app.core.vector_store import VectorStore
from app.lifecycle.registry import DocumentRegistry
from app.lifecycle.service import DocumentLifecycleService
from app.observability.logging import get_logger
from app.services.document_service import DocumentService
from app.services.rag_service import RAGService

logger = get_logger(__name__)


class RAGApplication:
    """Own shared provider clients and expose framework-neutral services."""

    def __init__(self, application_settings: Settings = settings) -> None:
        self.settings = application_settings
        self.initialized = False
        self.startup_error_type: str | None = None
        self._lock = RLock()
        self.embedding_client: Any | None = None
        self.vector_store: Any | None = None
        self.retriever: Any | None = None
        self.llm_client: Any | None = None
        self.rag_generator: Any | None = None
        self.doc_loader: Any | None = None
        self.chunker: Any | None = None
        self.registry: Any | None = None
        self.lifecycle_service: Any | None = None
        self.rag_service: RAGService | None = None
        self.document_service: DocumentService | None = None

    def initialize(self) -> None:
        with self._lock:
            if self.initialized:
                return
            logger.info("正在初始化 RAG 应用服务")
            try:
                self.embedding_client = UniversalEmbeddingClient(
                    self.settings.default_embedding_provider
                )
                self.vector_store = VectorStore(
                    collection_name=self.settings.collection_name,
                    uri=self.settings.milvus_uri,
                    token=self.settings.milvus_token,
                    db_name=self.settings.milvus_db_name,
                )
                self.retriever = Retriever(
                    self.vector_store,
                    self.embedding_client,
                )
                self.llm_client = UniversalLLMClient(
                    provider=self.settings.default_llm_provider
                )
                self.rag_generator = RAGGenerator(self.llm_client)
                self.doc_loader = UniversalDocumentLoader()
                self.chunker = DocumentChunker(
                    chunk_size=self.settings.chunk_size,
                    chunk_overlap=self.settings.chunk_overlap,
                )
                self.registry = DocumentRegistry(
                    self.settings.document_registry_path
                )
                self.lifecycle_service = DocumentLifecycleService(
                    loader=self.doc_loader,
                    chunker=self.chunker,
                    embedding_client=self.embedding_client,
                    vector_store=self.vector_store,
                    registry=self.registry,
                    upload_dir=self.settings.upload_dir,
                    tenant_id=self.settings.default_tenant_id,
                    collection_id=self.settings.collection_name,
                )
                self.rag_service = RAGService(
                    retriever=self.retriever,
                    rag_generator=self.rag_generator,
                    settings=self.settings,
                    lifecycle_service=self.lifecycle_service,
                )
                self.document_service = DocumentService(
                    lifecycle_service=self.lifecycle_service,
                    registry=self.registry,
                    tenant_id=self.settings.default_tenant_id,
                    collection_id=self.settings.collection_name,
                )
                self.startup_error_type = None
                self.initialized = True
                logger.info("RAG 应用服务初始化完成")
            except Exception as exc:
                self.startup_error_type = type(exc).__name__
                logger.exception(
                    "RAG 应用服务初始化失败",
                    event="application_startup_failed",
                    operation="application.initialize",
                    status="error",
                    error_type=type(exc).__name__,
                )
                self._close_resources()

    def _close_resources(self) -> None:
        lifecycle_service = self.lifecycle_service
        vector_store = self.vector_store
        self.lifecycle_service = None
        self.vector_store = None
        if lifecycle_service is not None:
            close_service = getattr(lifecycle_service, "close", None)
            if callable(close_service):
                close_service()
        elif vector_store is not None:
            close_store = getattr(vector_store, "close", None)
            if callable(close_store):
                close_store()

    def close(self) -> None:
        with self._lock:
            self._close_resources()
            self.initialized = False
            self.rag_service = None
            self.document_service = None

    def readiness(self) -> dict[str, Any]:
        components = {
            "application": "ready" if self.initialized else "unavailable",
            "milvus": "unknown",
            "embedding": "ready" if self.embedding_client else "unavailable",
            "llm": "ready" if self.llm_client else "unavailable",
            "registry": "ready" if self.registry else "unavailable",
        }
        if self.initialized and self.vector_store is not None:
            try:
                self.vector_store.client.list_collections()
                components["milvus"] = "ready"
            except Exception:
                components["milvus"] = "unavailable"
        ready = self.initialized and all(
            value == "ready" for value in components.values()
        )
        return {
            "status": "ready" if ready else "degraded",
            "ready": ready,
            "components": components,
            "error_type": None if ready else self.startup_error_type,
        }
