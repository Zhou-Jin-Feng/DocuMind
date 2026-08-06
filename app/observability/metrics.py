"""Prometheus RAG 指标定义与可选本地 HTTP 暴露服务。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from threading import RLock, Thread
from typing import Any
from wsgiref.simple_server import WSGIServer

from prometheus_client import CollectorRegistry, Counter, Histogram, start_http_server

from app.observability.logging import get_logger

logger = get_logger(__name__)

_LABEL_PATTERN = re.compile(r"[^a-zA-Z0-9_.:-]+")
_DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)


def _label(value: object, fallback: str = "unknown") -> str:
    """把代码侧枚举值限制为短、稳定的低基数字符串。"""

    normalized = _LABEL_PATTERN.sub("_", str(value or fallback).strip().lower())
    return (normalized or fallback)[:64]


class RAGMetrics:
    """RAG 应用指标集合；关闭时所有记录方法均为无操作。"""

    def __init__(
        self,
        enabled: bool = True,
        registry: CollectorRegistry | None = None,
    ) -> None:
        self.enabled = enabled
        self.registry = registry or CollectorRegistry(auto_describe=True)
        if not enabled:
            return

        self.queries_total = Counter(
            "rag_queries_total",
            "Total number of RAG queries.",
            ("provider", "status"),
            registry=self.registry,
        )
        self.query_duration = Histogram(
            "rag_query_duration_seconds",
            "End-to-end RAG query duration in seconds.",
            ("provider", "status"),
            buckets=_DEFAULT_BUCKETS,
            registry=self.registry,
        )
        self.no_context_total = Counter(
            "rag_no_context_total",
            "Queries that completed without usable retrieval context.",
            ("provider",),
            registry=self.registry,
        )
        self.component_errors_total = Counter(
            "rag_component_errors_total",
            "Errors grouped by stable component operation and exception type.",
            ("operation", "error_type"),
            registry=self.registry,
        )
        self.documents_uploaded_total = Counter(
            "rag_documents_uploaded_total",
            "Validated document upload attempts.",
            ("status",),
            registry=self.registry,
        )
        self.document_ingestion_duration = Histogram(
            "rag_document_ingestion_duration_seconds",
            "End-to-end document ingestion duration in seconds.",
            ("status",),
            buckets=_DEFAULT_BUCKETS,
            registry=self.registry,
        )
        self.chunks_created_total = Counter(
            "rag_chunks_created_total",
            "Chunks created by the document chunker.",
            registry=self.registry,
        )
        self.chunks_indexed_total = Counter(
            "rag_chunks_indexed_total",
            "Chunks upserted into the vector store.",
            registry=self.registry,
        )
        self.embedding_duration = Histogram(
            "rag_embedding_duration_seconds",
            "Embedding operation duration in seconds.",
            ("provider", "operation", "status"),
            buckets=_DEFAULT_BUCKETS,
            registry=self.registry,
        )
        self.retrieval_duration = Histogram(
            "rag_retrieval_duration_seconds",
            "Semantic retrieval duration in seconds.",
            ("provider", "status"),
            buckets=_DEFAULT_BUCKETS,
            registry=self.registry,
        )
        self.retrieval_result_count = Histogram(
            "rag_retrieval_result_count",
            "Number of retained retrieval results per query.",
            ("provider",),
            buckets=(0, 1, 2, 3, 5, 8, 10, 20),
            registry=self.registry,
        )
        self.llm_first_token_duration = Histogram(
            "rag_llm_first_token_duration_seconds",
            "Time to the first non-empty LLM text chunk.",
            ("provider", "status"),
            buckets=_DEFAULT_BUCKETS,
            registry=self.registry,
        )
        self.llm_total_duration = Histogram(
            "rag_llm_total_duration_seconds",
            "Total streaming LLM generation duration.",
            ("provider", "status"),
            buckets=_DEFAULT_BUCKETS,
            registry=self.registry,
        )

    def record_query(self, provider: str, status: str, duration_seconds: float) -> None:
        if not self.enabled:
            return
        labels = (_label(provider), _label(status))
        self.queries_total.labels(*labels).inc()
        self.query_duration.labels(*labels).observe(max(duration_seconds, 0.0))

    def record_no_context(self, provider: str) -> None:
        if self.enabled:
            self.no_context_total.labels(_label(provider)).inc()

    def record_component_error(self, operation: str, error_type: str) -> None:
        if self.enabled:
            self.component_errors_total.labels(
                _label(operation), _label(error_type)
            ).inc()

    def record_document_upload(self, status: str) -> None:
        if self.enabled:
            self.documents_uploaded_total.labels(_label(status)).inc()

    def record_document_ingestion(
        self,
        status: str,
        duration_seconds: float,
        *,
        chunks_created: int = 0,
        chunks_indexed: int = 0,
    ) -> None:
        if not self.enabled:
            return
        self.document_ingestion_duration.labels(_label(status)).observe(
            max(duration_seconds, 0.0)
        )
        if chunks_created > 0:
            self.chunks_created_total.inc(chunks_created)
        if chunks_indexed > 0:
            self.chunks_indexed_total.inc(chunks_indexed)

    def observe_embedding(
        self,
        provider: str,
        operation: str,
        status: str,
        duration_seconds: float,
    ) -> None:
        if self.enabled:
            self.embedding_duration.labels(
                _label(provider), _label(operation), _label(status)
            ).observe(max(duration_seconds, 0.0))

    def observe_retrieval(
        self,
        provider: str,
        status: str,
        duration_seconds: float,
        *,
        result_count: int | None = None,
    ) -> None:
        if not self.enabled:
            return
        normalized_provider = _label(provider)
        self.retrieval_duration.labels(
            normalized_provider, _label(status)
        ).observe(max(duration_seconds, 0.0))
        if result_count is not None:
            self.retrieval_result_count.labels(normalized_provider).observe(
                max(result_count, 0)
            )

    def observe_first_token(
        self,
        provider: str,
        status: str,
        duration_seconds: float,
    ) -> None:
        if self.enabled:
            self.llm_first_token_duration.labels(
                _label(provider), _label(status)
            ).observe(max(duration_seconds, 0.0))

    def observe_llm_total(
        self,
        provider: str,
        status: str,
        duration_seconds: float,
    ) -> None:
        if self.enabled:
            self.llm_total_duration.labels(
                _label(provider), _label(status)
            ).observe(max(duration_seconds, 0.0))


_METRICS_LOCK = RLock()
_DEFAULT_METRICS = RAGMetrics(enabled=False)


def configure_metrics(enabled: bool) -> RAGMetrics:
    """替换进程内默认指标集合；不会启动 HTTP 服务。"""

    global _DEFAULT_METRICS
    with _METRICS_LOCK:
        _DEFAULT_METRICS = RAGMetrics(enabled=enabled)
        return _DEFAULT_METRICS


def get_metrics() -> RAGMetrics:
    return _DEFAULT_METRICS


@dataclass(frozen=True, slots=True)
class MetricsServerHandle:
    host: str
    port: int
    server: WSGIServer
    thread: Thread


_SERVER_HANDLE: MetricsServerHandle | None = None


def start_metrics_server(
    host: str,
    port: int,
    metrics: RAGMetrics | None = None,
) -> MetricsServerHandle | None:
    """幂等启动指标 HTTP 服务；关闭指标时不监听端口。"""

    global _SERVER_HANDLE
    selected_metrics = metrics or get_metrics()
    if not selected_metrics.enabled:
        logger.info(
            "Metrics 已关闭",
            event="metrics_server_disabled",
            operation="metrics.serve",
            status="disabled",
        )
        return None

    with _METRICS_LOCK:
        if _SERVER_HANDLE is not None:
            if (_SERVER_HANDLE.host, _SERVER_HANDLE.port) != (host, port):
                raise RuntimeError("Metrics 服务已经在其他地址启动")
            return _SERVER_HANDLE
        try:
            server, thread = start_http_server(
                port=port,
                addr=host,
                registry=selected_metrics.registry,
            )
        except Exception as exc:
            logger.exception(
                "Metrics 服务启动失败",
                event="metrics_server_start_failed",
                operation="metrics.serve",
                status="error",
                error_type=type(exc).__name__,
                host=host,
                port=port,
            )
            return None
        _SERVER_HANDLE = MetricsServerHandle(host, port, server, thread)
        logger.info(
            "Metrics 服务已启动",
            event="metrics_server_started",
            operation="metrics.serve",
            status="success",
            host=host,
            port=port,
        )
        return _SERVER_HANDLE


def stop_metrics_server() -> None:
    """停止由本模块启动的服务，主要用于测试和受控关闭。"""

    global _SERVER_HANDLE
    with _METRICS_LOCK:
        if _SERVER_HANDLE is None:
            return
        _SERVER_HANDLE.server.shutdown()
        _SERVER_HANDLE.server.server_close()
        _SERVER_HANDLE.thread.join(timeout=2)
        _SERVER_HANDLE = None
