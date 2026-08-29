"""RAG 应用的依赖装配、共享资源所有权和就绪状态。"""

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
from app.services.retrieval_service import RetrievalService

logger = get_logger(__name__)


class RAGApplication:
    """
    统一创建并持有 Provider 客户端、存储适配器和框架无关服务。

    FastAPI 与兼容入口应复用同一个实例，避免重复建立 Milvus 连接或让服务层
    自行读取全局配置。
    """

    def __init__(self, application_settings: Settings = settings) -> None:
        self.settings = application_settings
        self.initialized = False
        self.startup_error_type: str | None = None
        self.llm_startup_error_type: str | None = None
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
        self.retrieval_service: RetrievalService | None = None
        self.document_service: DocumentService | None = None

    def initialize(self) -> None:
        """
        幂等初始化完整依赖图。

        启动失败会记录错误类型并释放已经创建的资源，由 readiness 对外返回
        degraded；这里不抛出，从而让健康端点仍可用于诊断和等待依赖恢复。
        """
        with self._lock:
            if self.initialized:
                return
            logger.info("正在初始化 RAG 应用服务")
            try:
                self.embedding_client = UniversalEmbeddingClient(
                    self.settings.default_embedding_provider,
                    connection_timeout_seconds=(
                        self.settings.retrieval_connection_timeout_seconds
                    ),
                    request_timeout_seconds=(
                        self.settings.retrieval_embedding_timeout_seconds
                    ),
                )
                self.vector_store = VectorStore(
                    collection_name=self.settings.collection_name,
                    uri=self.settings.milvus_uri,
                    token=self.settings.milvus_token,
                    db_name=self.settings.milvus_db_name,
                    connection_timeout_seconds=(
                        self.settings.retrieval_connection_timeout_seconds
                    ),
                )
                self.retriever = Retriever(
                    self.vector_store,
                    self.embedding_client,
                )
                self.doc_loader = UniversalDocumentLoader()
                self.chunker = DocumentChunker(
                    chunk_size=self.settings.chunk_size,
                    chunk_overlap=self.settings.chunk_overlap,
                )
                self.registry = DocumentRegistry(self.settings.document_registry_path)
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
                self.retrieval_service = RetrievalService(
                    retriever=self.retriever,
                    registry=self.registry,
                    tenant_id=self.settings.default_tenant_id,
                    collection_id=self.settings.collection_name,
                    max_concurrency=self.settings.retrieval_max_concurrency,
                    queue_timeout_seconds=(
                        self.settings.retrieval_queue_timeout_seconds
                    ),
                    embedding_timeout_seconds=(
                        self.settings.retrieval_embedding_timeout_seconds
                    ),
                    vector_search_timeout_seconds=(
                        self.settings.retrieval_milvus_timeout_seconds
                    ),
                    max_attempts=self.settings.retrieval_max_attempts,
                    retry_backoff_seconds=(
                        self.settings.retrieval_retry_backoff_seconds
                    ),
                )
                self.document_service = DocumentService(
                    lifecycle_service=self.lifecycle_service,
                    registry=self.registry,
                    tenant_id=self.settings.default_tenant_id,
                    collection_id=self.settings.collection_name,
                )
                try:
                    self.llm_client = UniversalLLMClient(
                        provider=self.settings.default_llm_provider
                    )
                    self.rag_generator = RAGGenerator(self.llm_client)
                    self.rag_service = RAGService(
                        retriever=self.retriever,
                        rag_generator=self.rag_generator,
                        settings=self.settings,
                        lifecycle_service=self.lifecycle_service,
                    )
                    self.llm_startup_error_type = None
                except Exception as exc:
                    self.llm_client = None
                    self.rag_generator = None
                    self.rag_service = None
                    self.llm_startup_error_type = type(exc).__name__
                    logger.warning(
                        "LLM 服务初始化失败，纯检索与文档能力保持可用",
                        event="llm_startup_degraded",
                        operation="application.initialize",
                        status="degraded",
                        error_type=type(exc).__name__,
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
        """按所有权释放资源，并兼容初始化只完成一部分的情况。"""
        lifecycle_service = self.lifecycle_service
        vector_store = self.vector_store
        self.lifecycle_service = None
        self.vector_store = None
        try:
            if lifecycle_service is not None:
                close_service = getattr(lifecycle_service, "close", None)
                if callable(close_service):
                    close_service()
            elif vector_store is not None:
                close_store = getattr(vector_store, "close", None)
                if callable(close_store):
                    close_store()
        except Exception as exc:
            logger.warning(
                "释放 RAG 应用资源时发生异常",
                event="application_resource_cleanup_failed",
                operation="application.close",
                status="error",
                error_type=type(exc).__name__,
            )
        finally:
            self.embedding_client = None
            self.retriever = None
            self.llm_client = None
            self.rag_generator = None
            self.doc_loader = None
            self.chunker = None
            self.registry = None
            self.retrieval_service = None
            self.llm_startup_error_type = None

    def close(self) -> None:
        """关闭共享资源，并把应用恢复为可重新初始化的状态。"""
        with self._lock:
            self._close_resources()
            self.initialized = False
            self.rag_service = None
            self.retrieval_service = None
            self.document_service = None

    def _readiness_timeout(self) -> float:
        return float(self.settings.readiness_probe_timeout_seconds)

    def _check_milvus(self) -> bool:
        """通过真实 RPC 检查 Milvus，而不是只判断客户端对象是否存在。"""
        client = getattr(self.vector_store, "client", None)
        list_collections = getattr(client, "list_collections", None)
        if not callable(list_collections):
            return False
        list_collections(timeout=self._readiness_timeout())
        return True

    def _check_embedding(self) -> bool:
        """执行 Embedding 客户端的真实探活检查。"""
        health_check = getattr(self.embedding_client, "health_check", None)
        if not callable(health_check):
            return False
        return bool(health_check(timeout_seconds=self._readiness_timeout()))

    def _check_llm_configuration(self) -> bool:
        """只验证 LLM 客户端和配置，不主动调用远程生成 API。"""
        client = self.llm_client
        return bool(
            client
            and getattr(client, "provider", None)
            and getattr(client, "model", None)
            and getattr(client, "client", None)
        )

    def readiness(self) -> dict[str, Any]:
        """
        聚合依赖状态：Milvus 与 Embedding 做真实探测，LLM 只检查配置。

        不向 LLM 发送生成请求可以避免健康检查产生费用；注册表当前只检查已
        初始化，不执行额外 SQL。任一必要组件不可用时整体状态为 degraded。
        """
        components = {
            "application": "ready" if self.initialized else "unavailable",
            "milvus": "unknown",
            "embedding": "unavailable",
            "llm": "ready" if self._check_llm_configuration() else "unavailable",
            "registry": "ready" if self.registry else "unavailable",
            "retrieval": "unavailable",
        }
        failures: list[str] = []
        if self.initialized and self.vector_store is not None:
            try:
                if self._check_milvus():
                    components["milvus"] = "ready"
                else:
                    components["milvus"] = "unavailable"
                    failures.append("milvus")
            except Exception as exc:
                components["milvus"] = "unavailable"
                failures.append("milvus")
                logger.warning(
                    "Milvus readiness probe failed",
                    event="dependency_readiness_failed",
                    component="milvus",
                    error_type=type(exc).__name__,
                )
        if self.initialized and self.embedding_client is not None:
            try:
                if self._check_embedding():
                    components["embedding"] = "ready"
                else:
                    failures.append("embedding")
            except Exception as exc:
                failures.append("embedding")
                logger.warning(
                    "Embedding readiness probe failed",
                    event="dependency_readiness_failed",
                    component="embedding",
                    error_type=type(exc).__name__,
                )
        if (
            self.initialized
            and self.retrieval_service is not None
            and components["milvus"] == "ready"
            and components["embedding"] == "ready"
            and components["registry"] == "ready"
        ):
            components["retrieval"] = "ready"
        for name, value in components.items():
            if (
                value == "unavailable"
                and name not in failures
                and name != "application"
            ):
                failures.append(name)
        ready = self.initialized and all(
            value == "ready" for value in components.values()
        )
        error_type = self.startup_error_type
        if not ready and error_type is None and failures:
            error_type = "dependency_unavailable"
        return {
            "status": "ready" if ready else "degraded",
            "ready": ready,
            "components": components,
            "error_type": error_type,
        }
