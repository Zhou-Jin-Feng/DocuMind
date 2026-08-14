"""Framework-neutral document ingestion and listing service."""

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
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
            active_index_id = document.get("active_index_id")
            index = (
                self.registry.get_index(active_index_id)
                if active_index_id
                else None
            )
            records.append(
                DocumentRecord(
                    document_key=str(document["document_key"]),
                    display_name=str(document["display_name"]),
                    status=str(index.get("status", "pending") if index else "pending"),
                    chunk_count=int(index.get("chunk_count", 0) if index else 0),
                    file_type=str(index["file_type"]) if index else None,
                    file_size_bytes=(
                        int(index["file_size_bytes"]) if index else None
                    ),
                    active_index_id=(
                        str(active_index_id) if active_index_id else None
                    ),
                    created_at=str(document["created_at"]),
                    updated_at=str(document["updated_at"]),
                )
            )
        return tuple(records)
