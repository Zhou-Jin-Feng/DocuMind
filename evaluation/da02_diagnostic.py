"""DA-02 diagnostic rerun with explicit Top-20 and evidence labels.

This runner is isolated from production indexing and candidate selection. It
reuses the production dense Retriever interface with an in-memory L2 adapter,
so a diagnostic run does not write to Milvus or alter the frozen DS-06 track.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping, Sequence
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.embedding_client import UniversalEmbeddingClient
from app.core.retriever import RetrievalResult, Retriever
from evaluation.ds06_runner import (
    DATASET_ROOT,
    FrozenCase,
    load_frozen_cases,
    load_frozen_corpus,
)
from evaluation.integration import InMemoryVectorStore

DEFAULT_OUTPUT = ROOT / "agent" / "review-20260923" / "r4-da02-diagnostic-v2.json"
HISTORICAL_REPORT = ROOT / "evaluation" / "reports" / "p2_ds06_holdout_v1.json"
SCHEMA_VERSION = "da02-diagnostic-v2"
TOP_K = 20
PRIMARY_MINIMUM_GRADE = 2
CONTEXTUAL_MINIMUM_GRADE = 1
EMBEDDING_REQUEST_TIMEOUT_SECONDS = 300.0

DIAGNOSTIC_CASE_IDS = (
    "REP-T13-01",
    "REP-T13-02",
    "REP-T13-03",
    "REP-T13-04",
    "REP-T13-09",
    "REP-T14-01",
    "REP-T14-03",
    "REP-T14-08",
    "REP-T15-03",
    "REP-T16-03",
    "REP-T16-06",
    "REP-T17-12",
)


def _embedding_transport_metadata(
    client: UniversalEmbeddingClient,
    *,
    embedded_text_count: int,
) -> dict[str, Any]:
    return {
        "client": "app.core.embedding_client.UniversalEmbeddingClient",
        "transport": "langchain_ollama.OllamaEmbeddings",
        "base_url": str(getattr(client, "base_url", "")),
        "input_mode": "single_text_per_request",
        "configured_batch_size": 1,
        "request_timeout_seconds": EMBEDDING_REQUEST_TIMEOUT_SECONDS,
        "initialization_dimension_probe": True,
        "embedded_text_count_excluding_probe": embedded_text_count,
        "server_environment": {
            name: os.environ.get(name)
            for name in (
                "OLLAMA_GPU_OVERHEAD",
                "OLLAMA_CONTEXT_LENGTH",
                "OLLAMA_FLASH_ATTENTION",
                "OLLAMA_KEEP_ALIVE",
            )
        },
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_sha256(path: Path) -> str:
    return _sha256_file(path)


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _safe_preview(value: str, limit: int = 180) -> str:
    normalized = " ".join(value.split())
    return normalized if len(normalized) <= limit else f"{normalized[:limit]}..."


def _first_rank(rows: Sequence[Mapping[str, Any]], labels: set[str]) -> int | None:
    for row in rows:
        if str(row.get("chunk_id") or "") in labels:
            return int(row["rank"])
    return None


def _recall(rows: Sequence[Mapping[str, Any]], labels: set[str], top_k: int) -> float:
    if not labels:
        return 0.0
    found = {
        str(row.get("chunk_id") or "")
        for row in rows[:top_k]
        if str(row.get("chunk_id") or "") in labels
    }
    return len(found) / len(labels)


def _mrr(rows: Sequence[Mapping[str, Any]], labels: set[str], top_k: int) -> float:
    rank = _first_rank(rows[:top_k], labels)
    return 1.0 / rank if rank else 0.0


def _source_locations(
    dataset_root: Path,
    corpus: Any,
) -> dict[str, dict[str, Any]]:
    """Map frozen chunks back to source character spans for audit output."""

    source_text_by_document: dict[str, str] = {}
    source_sha_by_document: dict[str, str] = {}
    for document in corpus.documents:
        metadata = document.metadata
        document_id = str(metadata.get("document_id") or metadata.get("id") or "")
        filename = str(metadata.get("source_file") or metadata.get("filename") or "")
        if not document_id or not filename:
            raise ValueError("冻结文档缺少 document_id 或 source_file")
        source_path = Path(dataset_root) / "documents" / filename
        source_text_by_document[document_id] = source_path.read_text(encoding="utf-8")
        source_sha_by_document[document_id] = _sha256_file(source_path)

    locations: dict[str, dict[str, Any]] = {}
    cursors: dict[str, int] = {}
    chunks = sorted(
        corpus.chunks,
        key=lambda item: (
            str(item.metadata.get("document_id") or ""),
            int(item.metadata.get("chunk_index", -1)),
        ),
    )
    for chunk in chunks:
        metadata = chunk.metadata
        chunk_id = str(metadata.get("chunk_id") or "")
        document_id = str(metadata.get("document_id") or "")
        source_text = source_text_by_document[document_id]
        cursor = cursors.get(document_id, 0)
        start = source_text.find(chunk.page_content, cursor)
        if start < 0:
            raise ValueError(f"无法映射冻结 Chunk 到原文: {chunk_id}")
        end = start + len(chunk.page_content)
        cursors[document_id] = max(start + 1, end - 100)
        locations[chunk_id] = {
            "source_file": str(metadata.get("source_file") or ""),
            "source_sha256": source_sha_by_document[document_id],
            "source_start": start,
            "source_end": end,
            "chunk_sha256": hashlib.sha256(
                chunk.page_content.encode("utf-8")
            ).hexdigest(),
            "content_preview": _safe_preview(chunk.page_content),
        }
    return locations


def _model_identity(client: Any) -> dict[str, Any]:
    """Read the local model digest when the provider exposes it."""

    identity: dict[str, Any] = {
        "provider": client.provider,
        "model": str(client.config.get("model") or ""),
        "dimension": int(client.config.get("dimensions") or 0),
    }
    if client.provider != "ollama":
        return identity

    base_url = str(getattr(client, "base_url", "")).rstrip("/")
    if not base_url:
        identity["identity_error"] = "Ollama base URL unavailable"
        return identity
    try:
        parsed = urlparse(base_url)
        opener = (
            build_opener()
            if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            else build_opener(ProxyHandler({}))
        )
        version_request = Request(
            f"{base_url}/api/version", headers={"Accept": "application/json"}
        )
        with opener.open(version_request, timeout=10) as response:
            version_payload = json.load(response)
        if isinstance(version_payload, Mapping):
            identity["ollama_version"] = str(version_payload.get("version") or "")
        request = Request(
            f"{base_url}/api/tags", headers={"Accept": "application/json"}
        )
        with opener.open(request, timeout=10) as response:
            payload = json.load(response)
        models = payload.get("models") if isinstance(payload, Mapping) else None
        configured = identity["model"]
        if isinstance(models, list):
            for model in models:
                if not isinstance(model, Mapping):
                    continue
                name = str(model.get("name") or "")
                if name == configured or name == f"{configured}:latest":
                    identity.update(
                        {
                            "name": name,
                            "digest": str(model.get("digest") or ""),
                            "size": model.get("size"),
                            "modified_at": model.get("modified_at"),
                        }
                    )
                    break
        if "digest" not in identity:
            identity["identity_error"] = "configured model not present in /api/tags"
    except (OSError, URLError, ValueError, TypeError, json.JSONDecodeError) as exc:
        identity["identity_error"] = type(exc).__name__
    return identity


def _historical_top3(path: Path) -> tuple[str, dict[str, list[str]]]:
    if not path.is_file():
        return "", {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    digest = _json_sha256(path)
    cases = payload.get("modes", {}).get("dense", {}).get("cases", [])
    result: dict[str, list[str]] = {}
    for case in cases:
        case_id = str(case.get("case_id") or "")
        result[case_id] = [
            str(item.get("chunk_id") or "") for item in case.get("retrieved", [])[:3]
        ]
    return digest, result


def summarize_case(
    case: FrozenCase,
    results: Sequence[RetrievalResult],
    *,
    top_k: int,
    locations: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    qrels = {qrel.chunk_id: qrel for qrel in case.qrels}
    primary_ids = {
        chunk_id
        for chunk_id, qrel in qrels.items()
        if qrel.grade >= PRIMARY_MINIMUM_GRADE
    }
    contextual_ids = {
        chunk_id
        for chunk_id, qrel in qrels.items()
        if qrel.grade >= CONTEXTUAL_MINIMUM_GRADE
    }
    target_document_ids = {qrel.document_id for qrel in qrels.values()}
    ranked: list[dict[str, Any]] = []
    for rank, result in enumerate(results[:top_k], 1):
        metadata = dict(result.metadata or {})
        chunk_id = str(metadata.get("chunk_id") or "")
        qrel = qrels.get(chunk_id)
        if qrel and qrel.grade >= PRIMARY_MINIMUM_GRADE:
            evidence_label = "primary"
        elif qrel and qrel.grade >= CONTEXTUAL_MINIMUM_GRADE:
            evidence_label = "contextual"
        else:
            evidence_label = "non_evidence"
        location = dict(locations.get(chunk_id, {}))
        ranked.append(
            {
                "rank": rank,
                "document_id": str(metadata.get("document_id") or ""),
                "chunk_id": chunk_id,
                "topic_id": metadata.get("topic_id"),
                "authority_state": metadata.get("authority_state"),
                "document_version": metadata.get("document_version"),
                "chunk_index": metadata.get("chunk_index"),
                "distance": (
                    float(result.distance) if result.distance is not None else None
                ),
                "evidence_label": evidence_label,
                "qrel_grade": qrel.grade if qrel else None,
                **location,
            }
        )

    top3 = min(3, top_k)
    target_document_first_rank = next(
        (
            int(row["rank"])
            for row in ranked
            if row["document_id"] in target_document_ids
        ),
        None,
    )
    primary_first_rank = _first_rank(ranked, primary_ids)
    contextual_first_rank = _first_rank(ranked, contextual_ids)
    observations = {
        "target_document_in_top3": target_document_first_rank is not None
        and target_document_first_rank <= top3,
        "target_document_in_top20": target_document_first_rank is not None
        and target_document_first_rank <= top_k,
        "primary_in_top3": primary_first_rank is not None
        and primary_first_rank <= top3,
        "primary_in_top20": primary_first_rank is not None
        and primary_first_rank <= top_k,
        "contextual_in_top3": contextual_first_rank is not None
        and contextual_first_rank <= top3,
        "contextual_in_top20": contextual_first_rank is not None
        and contextual_first_rank <= top_k,
        "contextual_only_in_top3": contextual_first_rank is not None
        and contextual_first_rank <= top3
        and (primary_first_rank is None or primary_first_rank > top3),
    }
    if primary_first_rank is None:
        diagnostic_reading = "primary_not_observed_through_top20"
    elif target_document_first_rank is not None and primary_first_rank > top3:
        diagnostic_reading = "target_document_present_primary_below_top3"
    else:
        diagnostic_reading = "primary_observed_in_top3"

    return {
        "case_id": case.case_id,
        "question": case.question,
        "category": case.category,
        "qrels": [qrel.__dict__ for qrel in case.qrels],
        "ranked": ranked,
        "metrics": {
            "primary_recall_at_3": _recall(ranked, primary_ids, top3),
            "primary_recall_at_20": _recall(ranked, primary_ids, top_k),
            "contextual_recall_at_3": _recall(ranked, contextual_ids, top3),
            "contextual_recall_at_20": _recall(ranked, contextual_ids, top_k),
            "primary_first_rank_at_3": (
                primary_first_rank
                if primary_first_rank and primary_first_rank <= top3
                else None
            ),
            "primary_first_rank_at_20": primary_first_rank,
            "contextual_first_rank_at_3": (
                contextual_first_rank
                if contextual_first_rank and contextual_first_rank <= top3
                else None
            ),
            "contextual_first_rank_at_20": contextual_first_rank,
            "primary_mrr_at_3": _mrr(ranked, primary_ids, top3),
            "primary_mrr_at_20": _mrr(ranked, primary_ids, top_k),
            "contextual_mrr_at_3": _mrr(ranked, contextual_ids, top3),
            "contextual_mrr_at_20": _mrr(ranked, contextual_ids, top_k),
        },
        "observations": observations,
        "diagnostic_reading": diagnostic_reading,
    }


def _aggregate(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    successful = [case for case in cases if case.get("status") == "success"]
    durations = [float(case["duration_ms"]) for case in successful]
    metric_names = (
        "primary_recall_at_3",
        "primary_recall_at_20",
        "contextual_recall_at_3",
        "contextual_recall_at_20",
        "primary_mrr_at_3",
        "primary_mrr_at_20",
        "contextual_mrr_at_3",
        "contextual_mrr_at_20",
    )
    metrics: dict[str, Any] = {}
    for name in metric_names:
        values = [float(case["metrics"][name]) for case in successful]
        metrics[name] = statistics.fmean(values) if values else None
    return {
        "case_count": len(cases),
        "successful_case_count": len(successful),
        "error_case_count": len(cases) - len(successful),
        "primary_in_top20_count": sum(
            bool(case.get("observations", {}).get("primary_in_top20"))
            for case in successful
        ),
        "contextual_only_in_top3_count": sum(
            bool(case.get("observations", {}).get("contextual_only_in_top3"))
            for case in successful
        ),
        "average_duration_ms": statistics.fmean(durations) if durations else None,
        "p50_duration_ms": _percentile(durations, 0.50),
        "p95_duration_ms": _percentile(durations, 0.95),
        "metrics": metrics,
    }


def run_diagnostic(
    *,
    output_path: Path,
    dataset_root: Path = DATASET_ROOT,
    provider: str = "ollama",
    top_k: int = TOP_K,
    historical_report: Path = HISTORICAL_REPORT,
) -> dict[str, Any]:
    if top_k < 20:
        raise ValueError("DA-02 诊断必须至少保留 Top-20")
    if output_path.exists():
        raise FileExistsError(f"拒绝覆盖已有诊断输出: {output_path}")

    all_cases = load_frozen_cases(dataset_root, split="holdout")
    cases_by_id = {case.case_id: case for case in all_cases}
    missing = [case_id for case_id in DIAGNOSTIC_CASE_IDS if case_id not in cases_by_id]
    if missing:
        raise ValueError(f"固定诊断案例缺失: {missing}")
    cases = [cases_by_id[case_id] for case_id in DIAGNOSTIC_CASE_IDS]

    corpus = load_frozen_corpus(dataset_root)
    locations = _source_locations(dataset_root, corpus)
    embedding = UniversalEmbeddingClient(
        provider,
        connection_timeout_seconds=10.0,
        request_timeout_seconds=EMBEDDING_REQUEST_TIMEOUT_SECONDS,
    )
    document_embeddings = embedding.embed_texts_batch(
        [chunk.page_content for chunk in corpus.chunks],
        batch_size=1,
        show_progress=False,
        max_retries=1,
    )
    if len(document_embeddings) != len(corpus.chunks):
        raise ValueError("文档向量数量与冻结 Chunk 数量不一致")
    dimension = {len(vector) for vector in document_embeddings}
    if len(dimension) != 1:
        raise ValueError("文档向量维度不一致")
    vector_store = InMemoryVectorStore(
        list(zip(corpus.chunks, document_embeddings, strict=True))
    )
    retriever = Retriever(vector_store, embedding)
    historical_digest, historical_cases = _historical_top3(historical_report)

    case_reports: list[dict[str, Any]] = []
    for case in cases:
        started = perf_counter()
        try:
            results = retriever.retrieve_semantic(case.question, top_k=top_k)
            report = summarize_case(case, results, top_k=top_k, locations=locations)
            rerun_top3 = [str(row["chunk_id"]) for row in report["ranked"][:3]]
            historical_top3 = historical_cases.get(case.case_id, [])
            report["historical_comparison"] = {
                "historical_report_sha256": historical_digest,
                "historical_top3_chunk_ids": historical_top3,
                "rerun_top3_chunk_ids": rerun_top3,
                "top3_exact_match": rerun_top3 == historical_top3,
            }
            report["status"] = "success"
        except Exception as exc:  # preserve completed cases and classify failures
            report = {
                "case_id": case.case_id,
                "question": case.question,
                "category": case.category,
                "status": "error",
                "error_type": type(exc).__name__,
            }
        report["duration_ms"] = round((perf_counter() - started) * 1000, 3)
        case_reports.append(report)

    code_files = {
        "diagnostic_runner": Path(__file__),
        "retriever": ROOT / "app" / "core" / "retriever.py",
        "embedding_client": ROOT / "app" / "core" / "embedding_client.py",
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": (
            "completed"
            if all(case.get("status") == "success" for case in case_reports)
            else "completed_with_case_errors"
        ),
        "scope": {
            "purpose": "DA-02 失败归因诊断，不用于候选选择或参数调优",
            "case_ids": list(DIAGNOSTIC_CASE_IDS),
            "source_split": "DS-06 frozen holdout",
            "retrieval_scope": "跨文档候选池；不等同于生产单文档检索范围",
            "historical_holdout_reopened_for_tuning": False,
        },
        "methodology": {
            "top_k": top_k,
            "primary_minimum_grade": PRIMARY_MINIMUM_GRADE,
            "contextual_minimum_grade": CONTEXTUAL_MINIMUM_GRADE,
            "distance": "squared L2",
            "adapter": "evaluation.integration.InMemoryVectorStore",
            "production_retriever_interface": "Retriever.retrieve_semantic",
            "embedding_request_mode": (
                "one text per /api/embed request; multi-input batching excluded "
                "after input-invariance verification"
            ),
            "candidate_variant": "none; current Dense baseline only",
            "source_mapping": "frozen Chunk content mapped back to source character spans",
        },
        "dataset": {
            "freeze_sha256": _json_sha256(Path(dataset_root) / "split_freeze.json"),
            "gold_sha256": _json_sha256(Path(dataset_root) / "gold_dataset.jsonl"),
            "documents_jsonl_sha256": _json_sha256(
                Path(dataset_root) / "documents.jsonl"
            ),
            "chunks_jsonl_sha256": _json_sha256(Path(dataset_root) / "chunks.jsonl"),
            "document_count": corpus.document_count,
            "chunk_count": corpus.chunk_count,
        },
        "runtime": {
            "embedding": _model_identity(embedding),
            "embedding_transport": _embedding_transport_metadata(
                embedding,
                embedded_text_count=(
                    len(document_embeddings)
                    + sum(case.get("status") == "success" for case in case_reports)
                ),
            ),
            "embedding_vector_count": len(document_embeddings),
            "embedding_dimension": next(iter(dimension)),
            "external_generation_calls": 0,
            "milvus_write": False,
        },
        "code_sha256": {name: _sha256_file(path) for name, path in code_files.items()},
        "aggregate": _aggregate(case_reports),
        "cases": case_reports,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return payload


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=DATASET_ROOT)
    parser.add_argument("--provider", default="ollama")
    parser.add_argument("--top-k", type=int, default=TOP_K)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--historical-report", type=Path, default=HISTORICAL_REPORT)
    args = parser.parse_args()
    try:
        result = run_diagnostic(
            output_path=args.output,
            dataset_root=args.dataset_root,
            provider=args.provider,
            top_k=args.top_k,
            historical_report=args.historical_report,
        )
        print(json.dumps(result["aggregate"], ensure_ascii=False, indent=2))
        return 0 if result["status"] == "completed" else 1
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"DA-02: ERROR\n- {type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
