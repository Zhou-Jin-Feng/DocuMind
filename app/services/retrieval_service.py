"""框架无关的单文档纯检索应用服务。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from app.lifecycle.models import LifecycleStatus


class DocumentNotFoundError(LookupError):
    """当前租户和 Collection 中不存在目标文档。"""


class DocumentIndexUnavailableError(RuntimeError):
    """目标文档当前没有可用于检索的活动索引。"""


class StaleDocumentIndexError(RuntimeError):
    """调用方持有的索引身份不再是文档的活动索引。"""


class RetrievalScopeViolationError(RuntimeError):
    """底层检索器返回了请求作用域之外的结果。"""


@dataclass(frozen=True, slots=True)
class RetrievalBatch:
    """一次纯检索的不可变文档范围和底层结果。"""

    document_key: str
    index_id: str
    source_sha256: str
    results: tuple[Any, ...]


class RetrievalService:
    """解析活动索引并在一个受控文档范围内执行 Dense 检索。"""

    def __init__(
        self,
        *,
        retriever: Any,
        registry: Any,
        tenant_id: str,
        collection_id: str,
    ) -> None:
        self.retriever = retriever
        self.registry = registry
        self.tenant_id = tenant_id
        self.collection_id = collection_id

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
                normalized_query,
                top_k=top_k,
                score_threshold=distance_threshold,
                metadata_filter=metadata_filter,
                result_predicate=belongs_to_scope,
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
            results=results,
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
            raise DocumentIndexUnavailableError(document_key)
        if active_index_id != expected_index_id:
            raise StaleDocumentIndexError(expected_index_id)

        index = self.registry.get_index(active_index_id)
        if index is None or (
            str(index.get("document_key", "")) != document_key
            or str(index.get("tenant_id", "")) != self.tenant_id
            or str(index.get("collection_id", "")) != self.collection_id
            or str(index.get("status", "")) != LifecycleStatus.ACTIVE.value
        ):
            raise DocumentIndexUnavailableError(document_key)
        return document, index
