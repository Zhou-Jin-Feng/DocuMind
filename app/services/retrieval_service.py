"""框架无关的单文档纯检索应用服务。"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePosixPath, PureWindowsPath
from threading import BoundedSemaphore
from typing import Any, Callable

from opentelemetry.trace import SpanKind

from app.lifecycle.models import LifecycleStatus
from app.observability.tracing import trace_span


class DocumentNotFoundError(LookupError):
    """当前租户和 Collection 中不存在目标文档。"""


class DocumentIndexUnavailableError(RuntimeError):
    """目标文档当前没有可用于检索的活动索引。"""


class DocumentOperationInProgressError(RuntimeError):
    """文档正在执行会暂时阻止纯检索的索引或删除操作。"""


class StaleDocumentIndexError(RuntimeError):
    """调用方持有的索引身份不再是文档的活动索引。"""


class RetrievalScopeViolationError(RuntimeError):
    """底层检索器返回了请求作用域之外的结果。"""


class InvalidRetrievalEvidenceError(RuntimeError):
    """底层结果缺少公共证据契约要求的稳定字段。"""


class RetrievalBusyError(RuntimeError):
    """纯检索并发已满，等待队列未能在固定时间内取得许可。"""


class RetrievalDependencyTimeoutError(TimeoutError):
    """Embedding 或 Milvus 在固定尝试次数内持续超时。"""


_CONTENT_HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")


@dataclass(frozen=True, slots=True)
class EvidenceChunk:
    """从内部结果白名单映射出的可追溯证据 Chunk。"""

    chunk_id: str
    content: str
    content_sha256: str
    source: str
    page_number: int | None
    distance: float
    rank: int

    @classmethod
    def from_result(cls, result: Any, *, rank: int) -> "EvidenceChunk":
        metadata = getattr(result, "metadata", {}) or {}
        chunk_id = str(metadata.get("chunk_id") or "")
        if not _CONTENT_HASH_PATTERN.fullmatch(chunk_id):
            raise InvalidRetrievalEvidenceError(
                "retrieval result has no stable SHA-256 chunk_id"
            )

        raw_content = getattr(result, "content", "")
        if not isinstance(raw_content, str) or not raw_content:
            raise InvalidRetrievalEvidenceError("retrieval result content is empty")
        content = raw_content

        raw_source = str(
            getattr(result, "source", "")
            or metadata.get("source_file")
            or metadata.get("source")
            or ""
        ).strip()
        source = PurePosixPath(PureWindowsPath(raw_source).name).name.strip()
        if not source:
            raise InvalidRetrievalEvidenceError("retrieval result source is empty")

        raw_page_number = getattr(result, "page_number", None)
        page_number = (
            raw_page_number
            if isinstance(raw_page_number, int) and raw_page_number > 0
            else None
        )
        raw_distance = getattr(result, "distance", None)
        if raw_distance is None:
            raise InvalidRetrievalEvidenceError("dense result has no L2 distance")
        distance = float(raw_distance)
        if not math.isfinite(distance) or distance < 0:
            raise InvalidRetrievalEvidenceError("dense result has invalid L2 distance")

        return cls(
            chunk_id=chunk_id,
            content=content,
            content_sha256=sha256(content.encode("utf-8")).hexdigest(),
            source=source,
            page_number=page_number,
            distance=distance,
            rank=rank,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "content_sha256": self.content_sha256,
            "source": self.source,
            "page_number": self.page_number,
            "distance": self.distance,
            "rank": self.rank,
        }


@dataclass(frozen=True, slots=True)
class RetrievalBatch:
    """一次纯检索的不可变文档范围和底层结果。"""

    document_key: str
    index_id: str
    source_sha256: str
    chunks: tuple[EvidenceChunk, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_key": self.document_key,
            "index_id": self.index_id,
            "source_sha256": self.source_sha256,
            "chunks": [chunk.to_dict() for chunk in self.chunks],
        }


class RetrievalService:
    """解析活动索引并在一个受控文档范围内执行 Dense 检索。"""

    def __init__(
        self,
        *,
        retriever: Any,
        registry: Any,
        tenant_id: str,
        collection_id: str,
        max_concurrency: int = 4,
        queue_timeout_seconds: float = 1.0,
        embedding_timeout_seconds: float = 15.0,
        vector_search_timeout_seconds: float = 5.0,
        max_attempts: int = 2,
        retry_backoff_seconds: float = 0.1,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive")
        for name, value in (
            ("queue_timeout_seconds", queue_timeout_seconds),
            ("embedding_timeout_seconds", embedding_timeout_seconds),
            ("vector_search_timeout_seconds", vector_search_timeout_seconds),
        ):
            if not math.isfinite(float(value)) or float(value) <= 0:
                raise ValueError(f"{name} must be a positive finite number")
        if not 1 <= max_attempts <= 3:
            raise ValueError("max_attempts must be between 1 and 3")
        if (
            not math.isfinite(float(retry_backoff_seconds))
            or float(retry_backoff_seconds) < 0
        ):
            raise ValueError("retry_backoff_seconds must be non-negative")
        self.retriever = retriever
        self.registry = registry
        self.tenant_id = tenant_id
        self.collection_id = collection_id
        self.queue_timeout_seconds = float(queue_timeout_seconds)
        self.embedding_timeout_seconds = float(embedding_timeout_seconds)
        self.vector_search_timeout_seconds = float(vector_search_timeout_seconds)
        self.max_attempts = max_attempts
        self.retry_backoff_seconds = float(retry_backoff_seconds)
        self._sleep = sleep
        self._slots = BoundedSemaphore(max_concurrency)

    def retrieve(
        self,
        query: str,
        *,
        document_key: str,
        expected_index_id: str,
        top_k: int,
        retrieval_mode: str,
        distance_threshold: float | None = None,
    ) -> RetrievalBatch:
        normalized_query = (query or "").strip()
        if not normalized_query:
            raise ValueError("query cannot be empty")
        if not 1 <= top_k <= 20:
            raise ValueError("top_k must be between 1 and 20")
        if retrieval_mode != "dense":
            raise ValueError("only dense retrieval is supported")
        if distance_threshold is not None and (
            not math.isfinite(float(distance_threshold))
            or float(distance_threshold) < 0
        ):
            raise ValueError("distance_threshold must be a non-negative finite number")

        acquired = self._slots.acquire(timeout=self.queue_timeout_seconds)
        if not acquired:
            raise RetrievalBusyError("retrieval concurrency limit reached")
        try:
            with trace_span(
                "retrieval.request",
                kind=SpanKind.SERVER,
                attributes={
                    "http.route": "/api/v1/retrieve",
                    "retrieval.mode": retrieval_mode,
                    "retrieval.top_k": top_k,
                    "retrieval.document_ref": document_key[:12],
                    "retrieval.index_ref": expected_index_id[:12],
                },
            ) as span:
                batch = self._retrieve_with_retries(
                    normalized_query,
                    document_key=document_key,
                    expected_index_id=expected_index_id,
                    top_k=top_k,
                    distance_threshold=distance_threshold,
                )
                if span.is_recording():
                    span.set_attribute("http.response.status_code", 200)
                    span.set_attribute("retrieval.result_count", len(batch.chunks))
                return batch
        finally:
            self._slots.release()

    def _retrieve_with_retries(
        self,
        query: str,
        *,
        document_key: str,
        expected_index_id: str,
        top_k: int,
        distance_threshold: float | None,
    ) -> RetrievalBatch:
        for attempt in range(1, self.max_attempts + 1):
            try:
                return self._retrieve_once(
                    query,
                    document_key=document_key,
                    expected_index_id=expected_index_id,
                    top_k=top_k,
                    distance_threshold=distance_threshold,
                )
            except Exception as exc:
                retryable = self._is_retryable_dependency_error(exc)
                if not retryable or attempt >= self.max_attempts:
                    if self._is_timeout_error(exc):
                        raise RetrievalDependencyTimeoutError(
                            "retrieval dependency timed out"
                        ) from exc
                    raise
                self._sleep(self.retry_backoff_seconds * (2 ** (attempt - 1)))
        raise RuntimeError("retrieval retry loop exited unexpectedly")

    def _retrieve_once(
        self,
        query: str,
        *,
        document_key: str,
        expected_index_id: str,
        top_k: int,
        distance_threshold: float | None,
    ) -> RetrievalBatch:
        document, index = self._resolve_active_index(
            document_key=document_key,
            expected_index_id=expected_index_id,
        )
        metadata_filter = {
            "tenant_id": self.tenant_id,
            "collection_id": self.collection_id,
            "document_key": document_key,
            "index_id": expected_index_id,
        }

        def belongs_to_scope(metadata: dict[str, Any]) -> bool:
            return all(
                str(metadata.get(field, "")) == str(value)
                for field, value in metadata_filter.items()
            )

        results = tuple(
            self.retriever.retrieve_semantic(
                query,
                top_k=top_k,
                score_threshold=distance_threshold,
                metadata_filter=metadata_filter,
                result_predicate=belongs_to_scope,
                embedding_timeout_seconds=self.embedding_timeout_seconds,
                vector_search_timeout_seconds=self.vector_search_timeout_seconds,
                embedding_max_attempts=1,
            )
        )
        if any(
            not belongs_to_scope(getattr(result, "metadata", {}) or {})
            for result in results
        ):
            raise RetrievalScopeViolationError(
                "retriever returned results outside the requested document index"
            )
        # The active pointer may change while Milvus is searching. Recheck it
        # before releasing evidence so a concurrent reindex fails closed.
        self._resolve_active_index(
            document_key=document_key,
            expected_index_id=expected_index_id,
        )

        return RetrievalBatch(
            document_key=str(document["document_key"]),
            index_id=str(index["index_id"]),
            source_sha256=str(index["source_sha256"]),
            chunks=tuple(
                EvidenceChunk.from_result(result, rank=rank)
                for rank, result in enumerate(results, start=1)
            ),
        )

    @staticmethod
    def _is_timeout_error(exc: Exception) -> bool:
        return isinstance(exc, TimeoutError) or type(exc).__name__ in {
            "APITimeoutError",
            "ConnectTimeout",
            "ReadTimeout",
            "TimeoutException",
        }

    @classmethod
    def _is_retryable_dependency_error(cls, exc: Exception) -> bool:
        if isinstance(exc, ConnectionError) or cls._is_timeout_error(exc):
            return True
        status_code = getattr(exc, "status_code", None)
        return (
            isinstance(status_code, int)
            and not isinstance(status_code, bool)
            and 500 <= status_code <= 599
        )

    def _resolve_active_index(
        self,
        *,
        document_key: str,
        expected_index_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        document = self.registry.get_document(document_key)
        if document is None or (
            str(document.get("tenant_id", "")) != self.tenant_id
            or str(document.get("collection_id", "")) != self.collection_id
        ):
            raise DocumentNotFoundError(document_key)

        active_index_id = str(document.get("active_index_id") or "")
        if not active_index_id:
            raise self._unavailable_index_error(document_key)
        if active_index_id != expected_index_id:
            raise StaleDocumentIndexError(expected_index_id)

        index = self.registry.get_index(active_index_id)
        if index is None:
            raise DocumentIndexUnavailableError(document_key)
        if (
            str(index.get("document_key", "")) != document_key
            or str(index.get("tenant_id", "")) != self.tenant_id
            or str(index.get("collection_id", "")) != self.collection_id
        ):
            raise RetrievalScopeViolationError(
                "active index is outside the requested document scope"
            )

        status = str(index.get("status", ""))
        if status in {
            LifecycleStatus.PENDING.value,
            LifecycleStatus.INDEXING.value,
            LifecycleStatus.DELETING.value,
        }:
            raise DocumentOperationInProgressError(document_key)
        if status != LifecycleStatus.ACTIVE.value:
            raise DocumentIndexUnavailableError(document_key)
        return document, index

    def _unavailable_index_error(self, document_key: str) -> RuntimeError:
        indexes = self.registry.list_indexes(
            document_key=document_key,
            tenant_id=self.tenant_id,
            collection_id=self.collection_id,
        )
        transitional_statuses = {
            LifecycleStatus.PENDING.value,
            LifecycleStatus.INDEXING.value,
            LifecycleStatus.DELETING.value,
        }
        if any(
            str(index.get("status", "")) in transitional_statuses for index in indexes
        ):
            return DocumentOperationInProgressError(document_key)
        return DocumentIndexUnavailableError(document_key)
