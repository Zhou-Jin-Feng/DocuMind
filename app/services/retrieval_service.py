"""框架无关的单文档纯检索应用服务。"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePosixPath, PureWindowsPath
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


class InvalidRetrievalEvidenceError(RuntimeError):
    """底层结果缺少公共证据契约要求的稳定字段。"""


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
            chunks=tuple(
                EvidenceChunk.from_result(result, rank=rank)
                for rank, result in enumerate(results, start=1)
            ),
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
