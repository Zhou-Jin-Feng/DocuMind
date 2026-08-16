"""Framework-neutral document lifecycle service."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from app.observability.logging import get_logger
from app.observability.metrics import get_metrics
from app.observability.tracing import mark_span_error, trace_span

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    document_key: str
    display_name: str
    status: str
    chunk_count: int
    file_type: str | None
    file_size_bytes: int | None
    active_index_id: str | None
    active_version_id: str | None
    version_count: int
    error_type: str | None
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DocumentIndexRecord:
    index_id: str
    document_version_id: str
    version_number: int
    status: str
    chunk_count: int
    error_type: str | None
    file_type: str
    file_size_bytes: int
    source_sha256: str
    created_at: str
    updated_at: str
    activated_at: str | None
    is_active: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DocumentDetail:
    summary: DocumentRecord
    indexes: tuple[DocumentIndexRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = self.summary.to_dict()
        payload["indexes"] = [index.to_dict() for index in self.indexes]
        return payload


class DocumentService:
    """Expose lifecycle operations as structured application data."""

    def __init__(
        self,
        *,
        lifecycle_service: Any,
        registry: Any,
        tenant_id: str,
        collection_id: str,
        metrics_getter: Callable[[], Any] = get_metrics,
    ) -> None:
        self.lifecycle_service = lifecycle_service
        self.registry = registry
        self.tenant_id = tenant_id
        self.collection_id = collection_id
        self.metrics_getter = metrics_getter

    def ingest(self, source_path: Path, *, display_name: str) -> Any:
        metrics = self.metrics_getter()
        started = perf_counter()
        extension = source_path.suffix.lower()
        file_size = source_path.stat().st_size
        metrics.record_document_upload("accepted")

        with trace_span("rag.document.ingest") as root_span:
            logger.info(
                "收到文档上传请求",
                event="document_upload_received",
                operation="rag.document.ingest",
                status="started",
                file_extension=extension,
                file_size_bytes=file_size,
            )
            try:
                result = self.lifecycle_service.ingest(
                    source_path,
                    display_name=display_name,
                )
                elapsed = perf_counter() - started
                is_noop = result.status == "noop"
                metrics.record_document_ingestion(
                    "noop" if is_noop else "success",
                    elapsed,
                    chunks_created=0 if is_noop else result.chunk_count,
                    chunks_indexed=0 if is_noop else result.chunk_count,
                )
                logger.info(
                    "文档处理完成",
                    event="document_indexing_completed",
                    operation="rag.document.ingest",
                    duration_ms=elapsed * 1000,
                    status="noop" if is_noop else "success",
                    chunk_count=result.chunk_count,
                )
                return result
            except Exception as exc:
                mark_span_error(root_span, exc)
                elapsed = perf_counter() - started
                metrics.record_component_error(
                    "rag.document.ingest", type(exc).__name__
                )
                metrics.record_document_ingestion("error", elapsed)
                logger.exception(
                    "文档处理失败",
                    event="document_indexing_completed",
                    operation="rag.document.ingest",
                    duration_ms=elapsed * 1000,
                    status="error",
                    error_type=type(exc).__name__,
                )
                raise

    def list_documents(self) -> tuple[DocumentRecord, ...]:
        records: list[DocumentRecord] = []
        documents = self.registry.list_documents(
            tenant_id=self.tenant_id,
            collection_id=self.collection_id,
        )
        for document in documents:
            indexes = self.registry.list_indexes(
                document_key=str(document["document_key"]),
                tenant_id=self.tenant_id,
                collection_id=self.collection_id,
            )
            records.append(self._build_summary(document, indexes))
        return tuple(records)

    def get_document(self, document_key: str) -> DocumentDetail:
        document = self._scoped_document(document_key)
        indexes = self.registry.list_indexes(
            document_key=document_key,
            tenant_id=self.tenant_id,
            collection_id=self.collection_id,
        )
        summary = self._build_summary(document, indexes)
        version_ids = []
        for index in indexes:
            version_id = str(index["document_version_id"])
            if version_id not in version_ids:
                version_ids.append(version_id)
        version_numbers = {
            version_id: number
            for number, version_id in enumerate(version_ids, start=1)
        }
        active_index_id = (
            str(document["active_index_id"])
            if document.get("active_index_id")
            else None
        )
        history = tuple(
            DocumentIndexRecord(
                index_id=str(index["index_id"]),
                document_version_id=str(index["document_version_id"]),
                version_number=version_numbers[str(index["document_version_id"])],
                status=str(index["status"]),
                chunk_count=int(index["chunk_count"]),
                error_type=self._index_error_type(index),
                file_type=str(index["file_type"]),
                file_size_bytes=int(index["file_size_bytes"]),
                source_sha256=str(index["source_sha256"]),
                created_at=str(index["created_at"]),
                updated_at=str(index["updated_at"]),
                activated_at=(
                    str(index["activated_at"])
                    if index.get("activated_at")
                    else None
                ),
                is_active=str(index["index_id"]) == active_index_id,
            )
            for index in reversed(indexes)
        )
        return DocumentDetail(summary=summary, indexes=history)

    def reindex(self, document_key: str) -> Any:
        started = perf_counter()
        metrics = self.metrics_getter()
        with trace_span("rag.document.reindex") as root_span:
            try:
                result = self.lifecycle_service.rebuild_document(document_key)
                metrics.record_document_ingestion(
                    "success",
                    perf_counter() - started,
                    chunks_created=result.chunk_count,
                    chunks_indexed=result.chunk_count,
                )
                logger.info(
                    "文档重新索引完成",
                    event="document_reindex_completed",
                    operation="rag.document.reindex",
                    status="success",
                    duration_ms=(perf_counter() - started) * 1000,
                    chunk_count=result.chunk_count,
                )
                return result
            except Exception as exc:
                mark_span_error(root_span, exc)
                metrics.record_component_error(
                    "rag.document.reindex", type(exc).__name__
                )
                metrics.record_document_ingestion(
                    "error", perf_counter() - started
                )
                logger.exception(
                    "文档重新索引失败",
                    event="document_reindex_completed",
                    operation="rag.document.reindex",
                    status="error",
                    error_type=type(exc).__name__,
                )
                raise

    def delete(self, document_key: str) -> Any:
        with trace_span("rag.document.delete") as root_span:
            try:
                result = self.lifecycle_service.delete_document(document_key)
                logger.info(
                    "文档删除完成",
                    event="document_delete_completed",
                    operation="rag.document.delete",
                    status="success",
                    deleted_index_count=result.deleted_index_count,
                    deleted_chunk_count=result.deleted_chunk_count,
                )
                return result
            except Exception as exc:
                mark_span_error(root_span, exc)
                self.metrics_getter().record_component_error(
                    "rag.document.delete", type(exc).__name__
                )
                logger.exception(
                    "文档删除失败",
                    event="document_delete_completed",
                    operation="rag.document.delete",
                    status="error",
                    error_type=type(exc).__name__,
                )
                raise

    def _scoped_document(self, document_key: str) -> dict[str, Any]:
        document = self.registry.get_document(document_key)
        if document is None or (
            document["tenant_id"] != self.tenant_id
            or document["collection_id"] != self.collection_id
        ):
            raise KeyError(f"Unknown document in the current scope: {document_key}")
        return document

    @staticmethod
    def _index_error_type(index: dict[str, Any]) -> str | None:
        error_type = index.get("error_type") or index.get(
            "last_operation_error_type"
        )
        return str(error_type) if error_type else None

    @staticmethod
    def _build_summary(
        document: dict[str, Any], indexes: tuple[dict, ...]
    ) -> DocumentRecord:
        active_index_id = (
            str(document["active_index_id"])
            if document.get("active_index_id")
            else None
        )
        active_index = next(
            (
                index
                for index in indexes
                if str(index["index_id"]) == active_index_id
            ),
            None,
        )
        current_index = active_index or (indexes[-1] if indexes else None)
        latest_failure = next(
            (
                index
                for index in reversed(indexes)
                if index["status"] in {"active", "failed"}
                and DocumentService._index_error_type(index)
            ),
            None,
        )
        version_count = len(
            {str(index["document_version_id"]) for index in indexes}
        )
        return DocumentRecord(
            document_key=str(document["document_key"]),
            display_name=str(document["display_name"]),
            status=str(current_index["status"] if current_index else "pending"),
            chunk_count=int(current_index["chunk_count"] if current_index else 0),
            file_type=(
                str(current_index["file_type"]) if current_index else None
            ),
            file_size_bytes=(
                int(current_index["file_size_bytes"]) if current_index else None
            ),
            active_index_id=(
                str(active_index_id) if active_index_id else None
            ),
            active_version_id=(
                str(active_index["document_version_id"])
                if active_index is not None
                else None
            ),
            version_count=version_count,
            error_type=(
                DocumentService._index_error_type(latest_failure)
                if latest_failure is not None
                else None
            ),
            created_at=str(document["created_at"]),
            updated_at=str(document["updated_at"]),
        )
