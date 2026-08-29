"""Deterministic quality regression for the single-document retrieval API."""

from __future__ import annotations

import json
import math
import platform
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath, PureWindowsPath
from time import perf_counter
from typing import Any, Mapping, Sequence

from langchain_core.documents import Document

from app import __version__
from app.api.schemas import RETRIEVAL_VERSION, RETRIEVE_SCHEMA_VERSION
from app.services.retrieval_service import RetrievalService
from evaluation.fingerprints import text_file_sha256
from evaluation.integration import (
    DeterministicEmbeddingClient,
    build_deterministic_retriever,
)
from evaluation.metrics import (
    mean_defined,
    precision_at_k,
    recall_at_k,
    reciprocal_rank_at_k,
)

_HASH_PATTERN = "0123456789abcdef"
_ROOT_FIELDS = {
    "dataset_name",
    "dataset_version",
    "top_k",
    "retrieval_mode",
    "documents",
    "cases",
}
_DOCUMENT_FIELDS = {
    "document_key",
    "index_id",
    "source_sha256",
    "source",
    "chunks",
}
_CHUNK_FIELDS = {"chunk_id", "page_number", "content"}
_CASE_FIELDS = {
    "id",
    "query",
    "document_key",
    "expected_index_id",
    "relevant_chunk_ids",
    "distance_threshold",
    "expect_empty",
}


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"retrieve quality JSON contains duplicate field: {key}")
        value[key] = item
    return value


def _exact_fields(payload: Mapping[str, Any], expected: set[str], name: str) -> None:
    actual = set(payload)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise ValueError(f"{name} fields differ: missing={missing}, unknown={unknown}")


def _hash(value: Any, name: str) -> str:
    normalized = str(value or "")
    if len(normalized) != 64 or any(char not in _HASH_PATTERN for char in normalized):
        raise ValueError(f"{name} must be a lowercase SHA-256 value")
    return normalized


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True, slots=True)
class QualityChunk:
    chunk_id: str
    page_number: int
    content: str


@dataclass(frozen=True, slots=True)
class QualityDocument:
    document_key: str
    index_id: str
    source_sha256: str
    source: str
    chunks: tuple[QualityChunk, ...]


@dataclass(frozen=True, slots=True)
class QualityCase:
    id: str
    query: str
    document_key: str
    expected_index_id: str
    relevant_chunk_ids: tuple[str, ...]
    distance_threshold: float | None
    expect_empty: bool


@dataclass(frozen=True, slots=True)
class RetrieveQualityDataset:
    dataset_name: str
    dataset_version: str
    top_k: int
    retrieval_mode: str
    documents: tuple[QualityDocument, ...]
    cases: tuple[QualityCase, ...]
    dataset_sha256: str
    documents_sha256: str


@dataclass(frozen=True, slots=True)
class RetrieveQualityCaseResult:
    case_id: str
    expected_chunk_ids: tuple[str, ...]
    retrieved_chunk_ids: tuple[str, ...]
    bottom_retriever_chunk_ids: tuple[str, ...]
    distances: tuple[float, ...]
    recall_at_k: float | None
    precision_at_k: float | None
    mrr_at_k: float | None
    ndcg_at_k: float | None
    empty_result_correct: float | None
    api_bottom_parity: float
    contamination_count: int
    duration_ms: float
    status: str = "success"
    error_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "expected_chunk_ids": list(self.expected_chunk_ids),
            "retrieved_chunk_ids": list(self.retrieved_chunk_ids),
            "bottom_retriever_chunk_ids": list(self.bottom_retriever_chunk_ids),
            "distances": list(self.distances),
            "metrics": {
                "recall_at_k": self.recall_at_k,
                "precision_at_k": self.precision_at_k,
                "mrr_at_k": self.mrr_at_k,
                "ndcg_at_k": self.ndcg_at_k,
                "empty_result_correct": self.empty_result_correct,
                "api_bottom_parity": self.api_bottom_parity,
            },
            "contamination_count": self.contamination_count,
            "duration_ms": round(self.duration_ms, 3),
            "status": self.status,
            "error_type": self.error_type,
        }


@dataclass(frozen=True, slots=True)
class RetrieveQualityReport:
    dataset_name: str
    top_k: int
    case_results: tuple[RetrieveQualityCaseResult, ...]
    metadata: Mapping[str, Any]
    metrics: Mapping[str, float | None]

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_schema_version": "retrieve-quality-report-v1",
            "dataset_name": self.dataset_name,
            "top_k": self.top_k,
            "case_count": len(self.case_results),
            "metadata": dict(self.metadata),
            "metrics": dict(self.metrics),
            "cases": [result.to_dict() for result in self.case_results],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n"

    def to_markdown(self) -> str:
        lines = [
            f"# Retrieve Quality Report: {self.dataset_name}",
            "",
            "> Scope: offline deterministic Dense regression. This report does not "
            "measure a production Embedding or Milvus deployment.",
            "",
            "## Metrics",
            "",
            "| Metric | Value |",
            "|---|---:|",
        ]
        for name, value in self.metrics.items():
            formatted = "null" if value is None else f"{value:.6f}"
            lines.append(f"| `{name}` | {formatted} |")
        lines.extend(
            [
                "",
                "## Reproduction Metadata",
                "",
                "| Setting | Value |",
                "|---|---|",
            ]
        )
        for name, value in self.metadata.items():
            lines.append(f"| `{name}` | `{json.dumps(value, ensure_ascii=False)}` |")
        lines.extend(
            [
                "",
                "## Cases",
                "",
                "| Case | Retrieved | Recall | MRR | nDCG | Parity | Contamination |",
                "|---|---|---:|---:|---:|---:|---:|",
            ]
        )
        for case in self.case_results:
            values = (
                "null" if value is None else f"{value:.4f}"
                for value in (case.recall_at_k, case.mrr_at_k, case.ndcg_at_k)
            )
            recall, mrr, ndcg = values
            lines.append(
                f"| `{case.case_id}` | {len(case.retrieved_chunk_ids)} | {recall} | "
                f"{mrr} | {ndcg} | {case.api_bottom_parity:.4f} | "
                f"{case.contamination_count} |"
            )
        return "\n".join(lines) + "\n"


class _QualityRegistry:
    def __init__(self, documents: Sequence[QualityDocument]) -> None:
        self.documents = {item.document_key: item for item in documents}
        self.indexes = {item.index_id: item for item in documents}

    def get_document(self, document_key: str) -> dict[str, Any] | None:
        item = self.documents.get(document_key)
        if item is None:
            return None
        return {
            "document_key": item.document_key,
            "tenant_id": "default",
            "collection_id": "rag_documents",
            "active_index_id": item.index_id,
        }

    def get_index(self, index_id: str) -> dict[str, Any] | None:
        item = self.indexes.get(index_id)
        if item is None:
            return None
        return {
            "index_id": item.index_id,
            "document_key": item.document_key,
            "tenant_id": "default",
            "collection_id": "rag_documents",
            "status": "active",
            "source_sha256": item.source_sha256,
        }

    def list_indexes(self, **kwargs: Any) -> tuple[dict[str, Any], ...]:
        document_key = kwargs.get("document_key")
        return tuple(
            value
            for item in self.documents.values()
            if document_key in {None, item.document_key}
            for value in (self.get_index(item.index_id),)
            if value is not None
        )


def load_retrieve_quality_dataset(path: str | Path) -> RetrieveQualityDataset:
    source = Path(path)
    try:
        payload = json.loads(
            source.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"retrieve quality dataset is invalid JSON: {source}") from exc
    if not isinstance(payload, Mapping):
        raise TypeError("retrieve quality dataset must be a JSON object")
    _exact_fields(payload, _ROOT_FIELDS, "dataset")
    top_k = payload["top_k"]
    if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= 20:
        raise ValueError("dataset top_k must be between 1 and 20")
    if payload["retrieval_mode"] != "dense":
        raise ValueError("retrieve quality dataset supports dense mode only")

    documents: list[QualityDocument] = []
    document_keys: set[str] = set()
    index_ids: set[str] = set()
    all_chunk_ids: set[str] = set()
    raw_documents = payload["documents"]
    if not isinstance(raw_documents, list) or len(raw_documents) < 2:
        raise ValueError("dataset requires at least two documents for isolation checks")
    for position, raw_document in enumerate(raw_documents):
        if not isinstance(raw_document, Mapping):
            raise TypeError("dataset document must be an object")
        _exact_fields(raw_document, _DOCUMENT_FIELDS, f"document[{position}]")
        document_key = _hash(raw_document["document_key"], "document_key")
        index_id = _hash(raw_document["index_id"], "index_id")
        if document_key in document_keys or index_id in index_ids:
            raise ValueError("dataset document or index identity is duplicated")
        source_name = _text(raw_document["source"], "source")
        if PurePosixPath(PureWindowsPath(source_name).name).name != source_name:
            raise ValueError("dataset source must be a basename")
        raw_chunks = raw_document["chunks"]
        if not isinstance(raw_chunks, list) or not raw_chunks:
            raise ValueError("dataset document requires chunks")
        chunks: list[QualityChunk] = []
        for chunk_position, raw_chunk in enumerate(raw_chunks):
            if not isinstance(raw_chunk, Mapping):
                raise TypeError("dataset chunk must be an object")
            _exact_fields(
                raw_chunk,
                _CHUNK_FIELDS,
                f"document[{position}].chunk[{chunk_position}]",
            )
            chunk_id = _hash(raw_chunk["chunk_id"], "chunk_id")
            page_number = raw_chunk["page_number"]
            if (
                not isinstance(page_number, int)
                or isinstance(page_number, bool)
                or page_number <= 0
            ):
                raise ValueError("chunk page_number must be a positive integer")
            if chunk_id in all_chunk_ids:
                raise ValueError("dataset chunk_id is duplicated")
            all_chunk_ids.add(chunk_id)
            chunks.append(
                QualityChunk(
                    chunk_id=chunk_id,
                    page_number=page_number,
                    content=_text(raw_chunk["content"], "chunk content"),
                )
            )
        document_keys.add(document_key)
        index_ids.add(index_id)
        documents.append(
            QualityDocument(
                document_key=document_key,
                index_id=index_id,
                source_sha256=_hash(raw_document["source_sha256"], "source_sha256"),
                source=source_name,
                chunks=tuple(chunks),
            )
        )

    documents_by_key = {item.document_key: item for item in documents}
    cases: list[QualityCase] = []
    case_ids: set[str] = set()
    raw_cases = payload["cases"]
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("dataset requires cases")
    for position, raw_case in enumerate(raw_cases):
        if not isinstance(raw_case, Mapping):
            raise TypeError("dataset case must be an object")
        _exact_fields(raw_case, _CASE_FIELDS, f"case[{position}]")
        case_id = _text(raw_case["id"], "case id")
        if case_id in case_ids:
            raise ValueError("dataset case id is duplicated")
        document_key = _hash(raw_case["document_key"], "case document_key")
        expected_index_id = _hash(
            raw_case["expected_index_id"], "case expected_index_id"
        )
        target = documents_by_key.get(document_key)
        if target is None or target.index_id != expected_index_id:
            raise ValueError("case document/index does not match a dataset document")
        relevant = raw_case["relevant_chunk_ids"]
        if not isinstance(relevant, list):
            raise TypeError("relevant_chunk_ids must be a list")
        relevant_ids = tuple(_hash(item, "relevant_chunk_id") for item in relevant)
        target_ids = {chunk.chunk_id for chunk in target.chunks}
        if len(relevant_ids) != len(set(relevant_ids)) or not set(
            relevant_ids
        ).issubset(target_ids):
            raise ValueError(
                "relevant chunks must be unique members of the target document"
            )
        threshold = raw_case["distance_threshold"]
        if threshold is not None and (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not math.isfinite(float(threshold))
            or float(threshold) < 0
        ):
            raise ValueError("distance_threshold must be null or non-negative")
        expect_empty = raw_case["expect_empty"]
        if not isinstance(expect_empty, bool):
            raise TypeError("expect_empty must be boolean")
        if expect_empty != (not relevant_ids):
            raise ValueError("expect_empty must agree with relevant_chunk_ids")
        case_ids.add(case_id)
        cases.append(
            QualityCase(
                id=case_id,
                query=_text(raw_case["query"], "case query"),
                document_key=document_key,
                expected_index_id=expected_index_id,
                relevant_chunk_ids=relevant_ids,
                distance_threshold=(
                    float(threshold) if threshold is not None else None
                ),
                expect_empty=expect_empty,
            )
        )

    if not any(case.relevant_chunk_ids for case in cases):
        raise ValueError("dataset requires at least one answerable case")
    if not any(case.expect_empty for case in cases):
        raise ValueError("dataset requires at least one expected-empty case")

    canonical_documents = json.dumps(
        raw_documents,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return RetrieveQualityDataset(
        dataset_name=_text(payload["dataset_name"], "dataset_name"),
        dataset_version=_text(payload["dataset_version"], "dataset_version"),
        top_k=top_k,
        retrieval_mode="dense",
        documents=tuple(documents),
        cases=tuple(cases),
        dataset_sha256=text_file_sha256(source),
        documents_sha256=sha256(canonical_documents).hexdigest(),
    )


def _ndcg_at_k(
    expected_chunk_ids: Sequence[str],
    retrieved_chunk_ids: Sequence[str],
    top_k: int,
) -> float | None:
    expected = set(expected_chunk_ids)
    if not expected:
        return None
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, chunk_id in enumerate(retrieved_chunk_ids[:top_k], start=1)
        if chunk_id in expected
    )
    ideal_count = min(len(expected), top_k)
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
    return dcg / ideal


def run_retrieve_quality(dataset: RetrieveQualityDataset) -> RetrieveQualityReport:
    documents: list[Document] = []
    target_chunk_ids: dict[str, set[str]] = {}
    for source_document in dataset.documents:
        target_chunk_ids[source_document.document_key] = {
            chunk.chunk_id for chunk in source_document.chunks
        }
        for chunk in source_document.chunks:
            documents.append(
                Document(
                    page_content=chunk.content,
                    metadata={
                        "tenant_id": "default",
                        "collection_id": "rag_documents",
                        "document_key": source_document.document_key,
                        "index_id": source_document.index_id,
                        "chunk_id": chunk.chunk_id,
                        "source_file": source_document.source,
                        "page_number": chunk.page_number,
                    },
                )
            )
    retriever = build_deterministic_retriever(documents)
    registry = _QualityRegistry(dataset.documents)
    service = RetrievalService(
        retriever=retriever,
        registry=registry,
        tenant_id="default",
        collection_id="rag_documents",
        max_attempts=1,
    )

    results: list[RetrieveQualityCaseResult] = []
    for case in dataset.cases:
        started = perf_counter()
        metadata_filter = {
            "tenant_id": "default",
            "collection_id": "rag_documents",
            "document_key": case.document_key,
            "index_id": case.expected_index_id,
        }

        def in_scope(metadata: Mapping[str, Any]) -> bool:
            return all(
                metadata.get(key) == value for key, value in metadata_filter.items()
            )

        try:
            batch = service.retrieve(
                case.query,
                document_key=case.document_key,
                expected_index_id=case.expected_index_id,
                top_k=dataset.top_k,
                retrieval_mode=dataset.retrieval_mode,
                distance_threshold=case.distance_threshold,
            )
            bottom = retriever.retrieve_semantic(
                case.query,
                top_k=dataset.top_k,
                score_threshold=case.distance_threshold,
                metadata_filter=metadata_filter,
                result_predicate=in_scope,
                embedding_timeout_seconds=15.0,
                vector_search_timeout_seconds=5.0,
                embedding_max_attempts=1,
            )
            retrieved_ids = tuple(chunk.chunk_id for chunk in batch.chunks)
            bottom_ids = tuple(
                str(item.metadata.get("chunk_id") or "") for item in bottom
            )
            contamination = sum(
                chunk_id not in target_chunk_ids[case.document_key]
                for chunk_id in retrieved_ids
            )
            results.append(
                RetrieveQualityCaseResult(
                    case_id=case.id,
                    expected_chunk_ids=case.relevant_chunk_ids,
                    retrieved_chunk_ids=retrieved_ids,
                    bottom_retriever_chunk_ids=bottom_ids,
                    distances=tuple(chunk.distance for chunk in batch.chunks),
                    recall_at_k=recall_at_k(
                        case.relevant_chunk_ids, retrieved_ids, dataset.top_k
                    ),
                    precision_at_k=precision_at_k(
                        case.relevant_chunk_ids, retrieved_ids, dataset.top_k
                    ),
                    mrr_at_k=reciprocal_rank_at_k(
                        case.relevant_chunk_ids, retrieved_ids, dataset.top_k
                    ),
                    ndcg_at_k=_ndcg_at_k(
                        case.relevant_chunk_ids, retrieved_ids, dataset.top_k
                    ),
                    empty_result_correct=(
                        float(not retrieved_ids) if case.expect_empty else None
                    ),
                    api_bottom_parity=float(retrieved_ids == bottom_ids),
                    contamination_count=contamination,
                    duration_ms=(perf_counter() - started) * 1000,
                )
            )
        except Exception as exc:
            results.append(
                RetrieveQualityCaseResult(
                    case_id=case.id,
                    expected_chunk_ids=case.relevant_chunk_ids,
                    retrieved_chunk_ids=(),
                    bottom_retriever_chunk_ids=(),
                    distances=(),
                    recall_at_k=None,
                    precision_at_k=None,
                    mrr_at_k=None,
                    ndcg_at_k=None,
                    empty_result_correct=None,
                    api_bottom_parity=0.0,
                    contamination_count=0,
                    duration_ms=(perf_counter() - started) * 1000,
                    status="error",
                    error_type=type(exc).__name__,
                )
            )

    total_retrieved = sum(len(item.retrieved_chunk_ids) for item in results)
    total_contamination = sum(item.contamination_count for item in results)
    successful = [item for item in results if item.status == "success"]
    metrics = {
        "recall_at_k": mean_defined([item.recall_at_k for item in successful]),
        "precision_at_k": mean_defined([item.precision_at_k for item in successful]),
        "mrr_at_k": mean_defined([item.mrr_at_k for item in successful]),
        "ndcg_at_k": mean_defined([item.ndcg_at_k for item in successful]),
        "no_answer_empty_accuracy": mean_defined(
            [item.empty_result_correct for item in successful]
        ),
        "api_bottom_parity_rate": mean_defined(
            [item.api_bottom_parity for item in successful]
        ),
        "contamination_free_rate": (
            1.0
            if total_retrieved == 0
            else 1.0 - (total_contamination / total_retrieved)
        ),
        "empty_result_rate": (
            sum(not item.retrieved_chunk_ids for item in successful) / len(successful)
            if successful
            else None
        ),
        "successful_case_rate": len(successful) / len(results),
    }
    embedder = DeterministicEmbeddingClient()
    metadata = {
        "evaluation_scope": "offline-deterministic-dense",
        "production_provider_conclusion": False,
        "dataset_version": dataset.dataset_version,
        "dataset_sha256": dataset.dataset_sha256,
        "documents_sha256": dataset.documents_sha256,
        "document_count": len(dataset.documents),
        "chunk_count": len(documents),
        "case_top_k_values": [dataset.top_k],
        "retrieval_mode": dataset.retrieval_mode,
        "score_threshold": "per-case",
        "embedding_provider": embedder.provider,
        "embedding_model": embedder.model_name,
        "embedding_dimension": embedder.dimension,
        "chunk_size": None,
        "chunk_overlap": None,
        "schema_version": RETRIEVE_SCHEMA_VERSION,
        "retrieval_version": RETRIEVAL_VERSION,
        "service_version": __version__,
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.system().lower(),
    }
    return RetrieveQualityReport(
        dataset_name=dataset.dataset_name,
        top_k=dataset.top_k,
        case_results=tuple(results),
        metadata=metadata,
        metrics=metrics,
    )


def quality_invariant_failures(report: RetrieveQualityReport) -> tuple[str, ...]:
    """Return failures that make a generated report unsafe as a baseline."""

    failures: list[str] = []
    failed_cases = [
        item.case_id for item in report.case_results if item.status != "success"
    ]
    if failed_cases:
        failures.append(f"case execution failed: {', '.join(failed_cases)}")
    for metric_name in (
        "api_bottom_parity_rate",
        "contamination_free_rate",
        "no_answer_empty_accuracy",
        "successful_case_rate",
    ):
        value = report.metrics.get(metric_name)
        if value != 1.0:
            failures.append(f"{metric_name} must equal 1.0, got {value!r}")
    return tuple(failures)
