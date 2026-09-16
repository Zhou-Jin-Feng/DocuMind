"""DS-06 graded-qrels evaluation for the frozen representative track.

The public retrieval API is intentionally not used here.  DS-06 evaluates the
same production retriever implementations over the frozen multi-Chunk corpus,
while keeping the evaluation contract independent from API request schemas.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping, Sequence

from langchain_core.documents import Document

from app.core.document_chunker import DocumentChunker
from app.core.retriever import (
    BM25Retriever,
    HybridRetriever,
    RetrievalResult,
    RerankingRetriever,
    Retriever,
)
from app.core.reranker import CrossEncoderReranker
from app.core.vector_store import VectorStore
from app.core.embedding_client import UniversalEmbeddingClient
from evaluation.adapters import RetrieverAdapter
from evaluation.representative_split_audit import (
    validate_frozen_representative_splits,
)

DATASET_ROOT = Path(__file__).resolve().parent / "datasets" / "p2_retrieval_v2"
DEFAULT_OUTPUT_ROOT = (
    Path(__file__).resolve().parents[1] / "artifacts" / "evaluation" / "ds06"
)
FREEZE_SHA256 = "49600e59d3525ac78ffadb61f667004db42752e0b80ad1bccce4e383ae4472a2"
GOLD_SHA256 = "7f2440695b6f575be045e066544009a765a308544982adb8618bf5004bf418a3"
SNAPSHOT_SCHEMA = "p2-ds06-evaluation-v1"
MODES = ("dense", "bm25", "hybrid", "rerank")


@dataclass(frozen=True)
class Qrel:
    document_id: str
    chunk_id: str
    grade: int


@dataclass(frozen=True)
class FrozenCase:
    case_id: str
    question: str
    split: str
    category: str
    answerable: bool
    qrels: tuple[Qrel, ...]


@dataclass(frozen=True)
class Corpus:
    documents: tuple[Document, ...]
    chunks: tuple[Document, ...]
    document_count: int
    chunk_count: int
    document_sha256: str
    chunk_sha256: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"DS-06 数据文件不存在: {path}")
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"DS-06 JSONL 第 {number} 行必须是对象: {path}")
        rows.append(value)
    if not rows:
        raise ValueError(f"DS-06 JSONL 不能为空: {path}")
    return rows


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _records_sha256(rows: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(_canonical_json(row))
        digest.update(b"\n")
    return digest.hexdigest()


def load_frozen_cases(
    dataset_root: Path = DATASET_ROOT,
    *,
    split: str | None = None,
    require_freeze: bool = True,
) -> list[FrozenCase]:
    """Load reviewed cases only after validating DS-05 freeze identity."""

    root = Path(dataset_root)
    if require_freeze:
        result = validate_frozen_representative_splits(root)
        if not result.get("ok"):
            raise ValueError(f"DS-05 冻结校验失败: {result.get('errors')}")
        if result.get("freeze_sha256") != FREEZE_SHA256:
            raise ValueError("DS-05 freeze_sha256 与 DS-06 预期不一致")
    rows = _read_jsonl(root / "gold_dataset.jsonl")
    cases: list[FrozenCase] = []
    seen: set[str] = set()
    for row in rows:
        case_id = str(row.get("id") or "").strip()
        if not case_id or case_id in seen:
            raise ValueError(f"DS-06 gold case ID 无效或重复: {case_id}")
        seen.add(case_id)
        case_split = str(row.get("split") or "").casefold()
        if case_split not in {"validation", "holdout"}:
            raise ValueError(f"DS-06 case split 无效: {case_id}")
        if split and case_split != split.casefold():
            continue
        raw_qrels = row.get("qrels")
        if not isinstance(raw_qrels, list):
            raise ValueError(f"DS-06 qrels 必须是数组: {case_id}")
        qrels: list[Qrel] = []
        for raw in raw_qrels:
            if not isinstance(raw, Mapping):
                raise ValueError(f"DS-06 qrel 必须是对象: {case_id}")
            grade = raw.get("relevance_grade")
            if (
                isinstance(grade, bool)
                or not isinstance(grade, int)
                or not 0 <= grade <= 3
            ):
                raise ValueError(f"DS-06 qrel grade 无效: {case_id}")
            qrels.append(
                Qrel(
                    document_id=str(raw.get("document_id") or ""),
                    chunk_id=str(raw.get("chunk_id") or ""),
                    grade=grade,
                )
            )
        answerable = bool(row.get("answerable"))
        if answerable != bool(qrels):
            raise ValueError(f"DS-06 answerable/qrels 不一致: {case_id}")
        cases.append(
            FrozenCase(
                case_id=case_id,
                question=str(row.get("question") or "").strip(),
                split=case_split,
                category=str(row.get("primary_category") or "general"),
                answerable=answerable,
                qrels=tuple(qrels),
            )
        )
    if not cases:
        raise ValueError(f"DS-06 没有 {split or '任何'} 冻结 case")
    return cases


def load_frozen_corpus(dataset_root: Path = DATASET_ROOT) -> Corpus:
    """Load the exact production Chunk identities from DS-04 output."""

    root = Path(dataset_root)
    document_rows = _read_jsonl(root / "documents.jsonl")
    chunk_rows = _read_jsonl(root / "chunks.jsonl")
    documents: list[Document] = []
    document_ids: set[str] = set()
    document_by_id: dict[str, Mapping[str, Any]] = {}
    for row in document_rows:
        document_id = str(row.get("id") or "")
        filename = str(row.get("filename") or "")
        if not document_id or document_id in document_ids:
            raise ValueError(f"DS-06 document ID 无效或重复: {document_id}")
        path = root / "documents" / filename
        if not path.is_file():
            raise FileNotFoundError(f"DS-06 文档缺失: {path}")
        content = path.read_text(encoding="utf-8")
        if hashlib.sha256(content.encode("utf-8")).hexdigest() != row.get(
            "content_sha256"
        ):
            raise ValueError(f"DS-06 文档哈希不匹配: {document_id}")
        metadata = dict(row)
        metadata.update({"document_id": document_id, "source_file": filename})
        documents.append(Document(page_content=content, metadata=metadata))
        document_ids.add(document_id)
        document_by_id[document_id] = row

    expected_chunks = {str(row.get("id") or ""): row for row in chunk_rows}
    if "" in expected_chunks or len(expected_chunks) != len(chunk_rows):
        raise ValueError("DS-06 Chunk manifest 存在空或重复 ID")
    generated_chunks = DocumentChunker(
        chunk_size=500, chunk_overlap=100
    ).chunk_documents_recursive(documents)
    generated_ids = {
        str(chunk.metadata.get("chunk_id") or "") for chunk in generated_chunks
    }
    if generated_ids != set(expected_chunks):
        raise ValueError("DS-06 生产 Chunk 重建后的 ID 与 manifest 不一致")
    chunks: list[Document] = []
    for chunk in generated_chunks:
        chunk_id = str(chunk.metadata["chunk_id"])
        document_id = str(chunk.metadata["document_id"])
        expected = expected_chunks[chunk_id]
        actual_hash = hashlib.sha256(chunk.page_content.encode("utf-8")).hexdigest()
        if actual_hash != expected.get("content_sha256"):
            raise ValueError(f"DS-06 Chunk 哈希不匹配: {chunk_id}")
        if len(chunk.page_content) != int(expected.get("char_count", -1)):
            raise ValueError(f"DS-06 Chunk 字符数不匹配: {chunk_id}")
        if int(chunk.metadata.get("chunk_index", -1)) != int(
            expected.get("chunk_index", -2)
        ):
            raise ValueError(f"DS-06 Chunk 序号不匹配: {chunk_id}")
        document_row = document_by_id[document_id]
        chunk.metadata.update(
            {
                "topic_id": document_row.get("topic_id"),
                "authority_state": document_row.get("authority_state"),
                "document_version": document_row.get("document_version"),
            }
        )
        chunks.append(chunk)
    if len(chunks) != sum(int(row.get("chunk_count", 0)) for row in document_rows):
        raise ValueError("DS-06 Chunk 总数与文档 manifest 不一致")
    return Corpus(
        documents=tuple(documents),
        chunks=tuple(chunks),
        document_count=len(documents),
        chunk_count=len(chunks),
        document_sha256=_sha256_file(root / "documents.jsonl"),
        chunk_sha256=_sha256_file(root / "chunks.jsonl"),
    )


def _relevant(qrels: Sequence[Qrel], *, minimum_grade: int = 2) -> dict[str, int]:
    return {qrel.chunk_id: qrel.grade for qrel in qrels if qrel.grade >= minimum_grade}


def _dcg(grades: Sequence[int]) -> float:
    return sum(
        (2**grade - 1) / math.log2(rank + 2) for rank, grade in enumerate(grades)
    )


def _case_metrics(
    case: FrozenCase, results: Sequence[RetrievalResult], top_k: int
) -> dict[str, float | None]:
    ranked_ids = [
        str((result.metadata or {}).get("chunk_id") or "") for result in results[:top_k]
    ]
    relevant = _relevant(case.qrels)
    all_grades = {qrel.chunk_id: qrel.grade for qrel in case.qrels}
    if not case.answerable:
        return {
            "recall_at_k": None,
            "mrr_at_k": None,
            "ndcg_at_k": None,
            "contextual_recall_at_k": None,
            "no_answer_empty_accuracy": float(not ranked_ids),
        }
    first = next(
        (rank for rank, chunk_id in enumerate(ranked_ids, 1) if chunk_id in relevant),
        None,
    )
    found = len(set(ranked_ids) & set(relevant))
    ideal = sorted((qrel.grade for qrel in case.qrels), reverse=True)[:top_k]
    actual = [all_grades.get(chunk_id, 0) for chunk_id in ranked_ids]
    return {
        "recall_at_k": found / len(relevant) if relevant else 0.0,
        "mrr_at_k": 1.0 / first if first else 0.0,
        "ndcg_at_k": _dcg(actual) / _dcg(ideal) if _dcg(ideal) else 0.0,
        "contextual_recall_at_k": (
            len(set(ranked_ids) & set(all_grades)) / len(all_grades)
            if all_grades
            else 0.0
        ),
        "no_answer_empty_accuracy": None,
    }


def _mean(values: Sequence[float | None]) -> float | None:
    defined = [float(value) for value in values if value is not None]
    return statistics.fmean(defined) if defined else None


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        raise ValueError("延迟样本不能为空")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _aggregate(case_results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    metric_names = (
        "recall_at_k",
        "mrr_at_k",
        "ndcg_at_k",
        "contextual_recall_at_k",
        "no_answer_empty_accuracy",
    )
    durations = [float(case["duration_ms"]) for case in case_results]
    return {
        **{
            name: _mean([case["metrics"].get(name) for case in case_results])
            for name in metric_names
        },
        "case_count": len(case_results),
        "successful_case_rate": sum(
            case["status"] == "success" for case in case_results
        )
        / len(case_results),
        "average_duration_ms": statistics.fmean(durations),
        "p50_duration_ms": _percentile(durations, 0.50),
        "p95_duration_ms": _percentile(durations, 0.95),
        "maximum_duration_ms": max(durations),
    }


def evaluate_adapter(
    adapter: RetrieverAdapter,
    cases: Sequence[FrozenCase],
    *,
    mode: str,
    top_k: int = 3,
    candidate_depth: int | None = None,
) -> dict[str, Any]:
    """Run one mode, retaining enough evidence to audit every result."""

    case_results: list[dict[str, Any]] = []
    for case in cases:
        started = perf_counter()
        results: list[RetrievalResult] = []
        error_type: str | None = None
        try:
            results = list(adapter.retrieve(case.question, top_k))
            status = "success"
        except Exception as exc:  # one failed case must not hide the rest
            status = "error"
            error_type = type(exc).__name__
        retrieved = [
            {
                "document_id": str((result.metadata or {}).get("document_id") or ""),
                "chunk_id": str((result.metadata or {}).get("chunk_id") or ""),
                "rank": result.rank,
                "distance": result.distance,
                "lexical_score": result.lexical_score,
                "fusion_score": result.fusion_score,
                "rerank_score": result.rerank_score,
            }
            for result in results
        ]
        metrics = (
            _case_metrics(case, results, top_k)
            if status == "success"
            else {
                "recall_at_k": None,
                "mrr_at_k": None,
                "ndcg_at_k": None,
                "contextual_recall_at_k": None,
                "no_answer_empty_accuracy": None,
            }
        )
        case_results.append(
            {
                "case_id": case.case_id,
                "question": case.question,
                "split": case.split,
                "category": case.category,
                "answerable": case.answerable,
                "qrels": [qrel.__dict__ for qrel in case.qrels],
                "retrieved": retrieved,
                "metrics": metrics,
                "duration_ms": round((perf_counter() - started) * 1000, 3),
                "status": status,
                "error_type": error_type,
            }
        )
    return {
        "schema_version": SNAPSHOT_SCHEMA,
        "mode": mode,
        "candidate_depth": candidate_depth,
        "case_count": len(case_results),
        "metrics": _aggregate(case_results),
        "cases": case_results,
    }


class FixedDepthRerankingRetriever:
    """Rerank exactly N hybrid candidates, unlike multiplier-based production wrapper."""

    def __init__(self, base: HybridRetriever, reranker: Any, candidate_depth: int):
        if candidate_depth <= 0:
            raise ValueError("candidate_depth 必须大于 0")
        self.base = base
        self.reranker = reranker
        self.candidate_depth = candidate_depth

    def retrieve_hybrid(
        self, query: str, top_k: int = 3, **kwargs: Any
    ) -> list[RetrievalResult]:
        candidates = self.base.retrieve_hybrid(
            query, top_k=self.candidate_depth, **kwargs
        )
        return self.reranker.rerank(query, candidates, top_k=top_k)


def _build_real_adapters(
    corpus: Corpus,
    *,
    provider: str,
    milvus_uri: str,
    collection_name: str,
    reranker_model: str,
    reranker_device: str | None,
    reranker_local_files_only: bool,
    reranker_batch_size: int,
) -> tuple[dict[str, RetrieverAdapter], dict[str, Any], Any]:
    embedding = UniversalEmbeddingClient(provider)
    store = VectorStore(collection_name=collection_name, uri=milvus_uri)
    chunk_list = list(corpus.chunks)
    embeddings = embedding.embed_texts_batch(
        [chunk.page_content for chunk in chunk_list], show_progress=True
    )
    store.ensure_embedding_space(
        embedding.provider, embedding.config["model"], len(embeddings[0])
    )
    store.add_documents(chunk_list, embeddings)
    dense = Retriever(store, embedding)
    lexical = BM25Retriever(chunk_list)
    hybrid = HybridRetriever(
        dense,
        lexical,
        rrf_k=60,
        dense_weight=1.0,
        lexical_weight=1.0,
        candidate_multiplier=5,
    )
    reranker = CrossEncoderReranker(
        reranker_model,
        batch_size=reranker_batch_size,
        device=reranker_device,
        local_files_only=reranker_local_files_only,
    )
    adapters = {
        "dense": RetrieverAdapter(dense),
        "bm25": RetrieverAdapter(lexical, retrieval_method="retrieve_lexical"),
        "hybrid": RetrieverAdapter(hybrid, retrieval_method="retrieve_hybrid"),
    }
    # candidate_depth is replaced per validation choice by run_evaluation.
    adapters["rerank"] = RetrieverAdapter(
        FixedDepthRerankingRetriever(hybrid, reranker, 5),
        retrieval_method="retrieve_hybrid",
    )
    return (
        adapters,
        {
            "embedding_provider": embedding.provider,
            "embedding_model": embedding.config["model"],
            "embedding_dimension": len(embeddings[0]),
            "reranker_model": reranker_model,
            "reranker_device": reranker_device or "auto",
            "reranker_local_files_only": reranker_local_files_only,
            "reranker_batch_size": reranker_batch_size,
            "collection_name": collection_name,
        },
        (store, embedding, reranker, hybrid),
    )


def _replace_rerank_depth(adapter: RetrieverAdapter, depth: int) -> None:
    wrapper = adapter.retriever
    if not isinstance(wrapper, FixedDepthRerankingRetriever):
        raise TypeError("rerank adapter 类型不匹配")
    wrapper.candidate_depth = depth


def _validation_choice(reports: Mapping[int, Mapping[str, Any]]) -> int:
    """Choose depth on validation only: MRR, nDCG, then latency."""

    def key(item: tuple[int, Mapping[str, Any]]) -> tuple[float, float, float, int]:
        depth, report = item
        metrics = report["metrics"]
        return (
            float(metrics.get("mrr_at_k") or 0.0),
            float(metrics.get("ndcg_at_k") or 0.0),
            -float(metrics.get("p95_duration_ms") or math.inf),
            -depth,
        )

    return max(reports.items(), key=key)[0]


def build_decision(
    reports: Mapping[str, Mapping[str, Any]],
    *,
    selected_depth: int,
    p95_additive_limit_ms: float = 750.0,
) -> dict[str, Any]:
    dense = reports["dense"]["metrics"]
    candidates: dict[str, Any] = {}
    for mode in ("bm25", "hybrid", "rerank"):
        metrics = reports[mode]["metrics"]
        failures: list[str] = []
        for field in ("recall_at_k", "mrr_at_k", "ndcg_at_k"):
            if float(metrics.get(field) or 0.0) < float(dense.get(field) or 0.0):
                failures.append(f"{field} regression")
        if float(metrics.get("successful_case_rate") or 0.0) < 1.0:
            failures.append("successful_case_rate < 1.0")
        p95 = float(metrics.get("p95_duration_ms") or math.inf)
        dense_p95 = float(dense.get("p95_duration_ms") or math.inf)
        if p95 > dense_p95 + p95_additive_limit_ms:
            failures.append("p95 increase > 750 ms")
        if p95 > dense_p95 * 2:
            failures.append("p95 exceeds 2x dense")
        quality_gain = max(
            float(metrics.get("mrr_at_k") or 0.0) - float(dense.get("mrr_at_k") or 0.0),
            float(metrics.get("ndcg_at_k") or 0.0)
            - float(dense.get("ndcg_at_k") or 0.0),
        )
        if quality_gain <= 0.0:
            failures.append("no strict quality gain over dense")
        candidates[mode] = {
            "eligible": not failures,
            "selected_depth": selected_depth if mode == "rerank" else None,
            "quality_gain_over_dense": quality_gain,
            "failures": failures,
            "metrics": metrics,
        }
    eligible = [mode for mode, value in candidates.items() if value["eligible"]]
    return {
        "schema_version": SNAPSHOT_SCHEMA,
        "decision": "GO" if eligible else "NO_GO",
        "selected_candidate": eligible[0] if eligible else None,
        "selected_rerank_depth": selected_depth,
        "public_contract_action": (
            "keep Schema 1.0 and dense-v1"
            if not eligible
            else "review selected candidate before API change"
        ),
        "dense_metrics": dense,
        "candidates": candidates,
    }


def finalize_decision(
    validation_report_path: Path,
    holdout_report_path: Path,
    *,
    output_dir: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    """Build the immutable candidate decision from validation and holdout reports."""

    validation = json.loads(Path(validation_report_path).read_text(encoding="utf-8"))
    holdout = json.loads(Path(holdout_report_path).read_text(encoding="utf-8"))
    if validation.get("split") != "validation" or holdout.get("split") != "holdout":
        raise ValueError("DS-06 decision requires validation and holdout reports")
    selected_depth = validation.get("selected_rerank_depth")
    if selected_depth not in {5, 8}:
        raise ValueError("validation report lacks a frozen reranker depth")
    if holdout.get("selected_rerank_depth") != selected_depth:
        raise ValueError("holdout reranker depth differs from validation freeze")
    validation_dataset = validation.get("dataset")
    holdout_dataset = holdout.get("dataset")
    if validation_dataset != holdout_dataset:
        raise ValueError("validation and holdout dataset fingerprints differ")
    holdout_modes = holdout.get("modes")
    if not isinstance(holdout_modes, Mapping) or any(
        mode not in holdout_modes for mode in MODES
    ):
        raise ValueError("holdout report lacks all four retrieval modes")
    decision = build_decision(
        {mode: holdout_modes[mode] for mode in MODES}, selected_depth=selected_depth
    )
    payload = {
        "schema_version": SNAPSHOT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": holdout_dataset,
        "validation_report": {
            "path": str(Path(validation_report_path).as_posix()),
            "selected_rerank_depth": selected_depth,
            "metrics": {
                mode: validation["modes"][mode]["metrics"]
                for mode in ("dense", "bm25", "hybrid")
            },
            "reranker_depths": {
                depth: report["metrics"]
                for depth, report in validation["modes"]
                .get("rerank_depths", {})
                .items()
            },
        },
        "holdout_report": {
            "path": str(Path(holdout_report_path).as_posix()),
            "metrics": {mode: holdout_modes[mode]["metrics"] for mode in MODES},
        },
        "decision": decision,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "p2_ds06_final_decision_v1.json"
    markdown_path = output_dir / "p2_ds06_final_decision_v1.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(
        render_decision_markdown(payload), encoding="utf-8", newline="\n"
    )
    return payload


def render_decision_markdown(payload: Mapping[str, Any]) -> str:
    decision = payload["decision"]
    lines = [
        "# DS-06 Retrieval Evaluation Decision",
        "",
        f"Decision: **{decision['decision']}**",
        "",
        f"Selected candidate: `{decision.get('selected_candidate') or 'none'}`",
        "",
        f"Selected Reranker depth (validation only): `{decision['selected_rerank_depth']}`",
        "",
        "## Holdout Comparison",
        "",
        "| Mode | Eligible | Recall@3 | MRR@3 | nDCG@3 | P95 ms | Failures |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for mode in MODES:
        candidate = decision["candidates"].get(mode, {})
        metrics = (
            decision["dense_metrics"]
            if mode == "dense"
            else candidate.get("metrics", {})
        )
        fmt = lambda value: "N/A" if value is None else f"{float(value):.4f}"
        lines.append(
            f"| `{mode}` | {('yes' if mode == 'dense' or candidate.get('eligible') else 'no')} | "
            f"{fmt(metrics.get('recall_at_k'))} | {fmt(metrics.get('mrr_at_k'))} | "
            f"{fmt(metrics.get('ndcg_at_k'))} | {fmt(metrics.get('p95_duration_ms'))} | "
            f"{len(candidate.get('failures', []))} |"
        )
    lines.extend(
        [
            "",
            "## Gate",
            "",
            "- Chunk-level graded qrels use grade >= 2 as direct evidence for Recall/MRR.",
            "- nDCG retains all reviewed grades 0-3; no-answer cases are excluded from ranking means.",
            "- A candidate must avoid quality regression, keep successful-case rate at 1.0, stay within +750 ms and 2x Dense P95, and show a strict quality gain.",
            "- A `NO_GO` result keeps public Schema `1.0` and `dense-v1` unchanged.",
            "",
        ]
    )
    for mode in ("bm25", "hybrid", "rerank"):
        failures = decision["candidates"][mode].get("failures", [])
        lines.append(f"### {mode}")
        lines.append("")
        if failures:
            lines.extend(f"- {failure}" for failure in failures)
        else:
            lines.append("- Eligible under DS-06 gate.")
        lines.append("")
    return "\n".join(lines)


def run_evaluation(
    *,
    split: str,
    dataset_root: Path = DATASET_ROOT,
    provider: str = "ollama",
    milvus_uri: str = "http://127.0.0.1:19530",
    collection_name: str = "ds06_rep_v1_49600e59",
    reranker_model: str = "BAAI/bge-reranker-base",
    reranker_device: str | None = "cpu",
    reranker_local_files_only: bool = True,
    reranker_batch_size: int = 8,
    top_k: int = 3,
    selected_depth: int | None = None,
    output_dir: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    """Run validation or holdout; holdout requires a frozen depth."""

    if split not in {"validation", "holdout"}:
        raise ValueError("split 必须是 validation 或 holdout")
    cases = load_frozen_cases(dataset_root, split=split)
    corpus = load_frozen_corpus(dataset_root)
    corpus_chunk_ids = {str(chunk.metadata["chunk_id"]) for chunk in corpus.chunks}
    corpus_document_ids = {
        str(document.metadata["document_id"]) for document in corpus.documents
    }
    for case in cases:
        for qrel in case.qrels:
            if (
                qrel.chunk_id not in corpus_chunk_ids
                or qrel.document_id not in corpus_document_ids
            ):
                raise ValueError(f"DS-06 qrel 引用冻结语料之外的身份: {case.case_id}")
    adapters, runtime, resources = _build_real_adapters(
        corpus,
        provider=provider,
        milvus_uri=milvus_uri,
        collection_name=collection_name,
        reranker_model=reranker_model,
        reranker_device=reranker_device,
        reranker_local_files_only=reranker_local_files_only,
        reranker_batch_size=reranker_batch_size,
    )
    try:
        reports: dict[str, Any] = {}
        for mode in ("dense", "bm25", "hybrid"):
            reports[mode] = evaluate_adapter(
                adapters[mode], cases, mode=mode, top_k=top_k
            )
        if split == "holdout" and selected_depth not in {5, 8}:
            raise ValueError(
                "holdout 必须提供 validation 冻结的 Reranker depth (5 或 8)"
            )
        depths = (5, 8) if split == "validation" else (selected_depth,)
        depth_reports: dict[int, dict[str, Any]] = {}
        for depth in depths:
            assert depth is not None
            _replace_rerank_depth(adapters["rerank"], depth)
            depth_reports[depth] = evaluate_adapter(
                adapters["rerank"],
                cases,
                mode="rerank",
                top_k=top_k,
                candidate_depth=depth,
            )
        selected_depth = (
            _validation_choice(depth_reports)
            if split == "validation"
            else selected_depth
        )
        reports["rerank_depths"] = {
            str(depth): report for depth, report in depth_reports.items()
        }
        reports["rerank"] = depth_reports[selected_depth]
        decision = None
    finally:
        for adapter in adapters.values():
            adapter.close()
        resources[2].close()
        resources[0].close()
    output = {
        "schema_version": SNAPSHOT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "split": split,
        "dataset": {
            "freeze_sha256": FREEZE_SHA256,
            "gold_sha256": GOLD_SHA256,
            "document_count": corpus.document_count,
            "chunk_count": corpus.chunk_count,
            "documents_jsonl_sha256": corpus.document_sha256,
            "chunks_jsonl_sha256": corpus.chunk_sha256,
        },
        "runtime": runtime,
        "top_k": top_k,
        "selected_rerank_depth": selected_depth,
        "modes": reports,
        "decision": decision,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"p2_ds06_{split}_v1.json"
    path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return output


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("validate", "validation", "holdout", "finalize")
    )
    parser.add_argument("--dataset-root", type=Path, default=DATASET_ROOT)
    parser.add_argument("--provider", default="ollama")
    parser.add_argument("--milvus-uri", default="http://127.0.0.1:19530")
    parser.add_argument("--collection-name", default="ds06_rep_v1_49600e59")
    parser.add_argument("--reranker-model", default="BAAI/bge-reranker-base")
    parser.add_argument("--reranker-device", default="cpu")
    parser.add_argument("--reranker-batch-size", type=int, default=8)
    parser.add_argument("--allow-reranker-download", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--selected-depth", type=int, choices=(5, 8))
    parser.add_argument("--validation-report", type=Path)
    parser.add_argument("--holdout-report", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "validate":
            result = validate_frozen_representative_splits(args.dataset_root)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result.get("ok") else 1
        if args.command == "finalize":
            if not args.validation_report or not args.holdout_report:
                raise ValueError(
                    "finalize 需要 --validation-report 和 --holdout-report"
                )
            result = finalize_decision(
                args.validation_report, args.holdout_report, output_dir=args.output_dir
            )
            print(render_decision_markdown(result))
            return 0 if result["decision"]["decision"] == "GO" else 1
        result = run_evaluation(
            split=args.command,
            dataset_root=args.dataset_root,
            provider=args.provider,
            milvus_uri=args.milvus_uri,
            collection_name=args.collection_name,
            reranker_model=args.reranker_model,
            reranker_device=args.reranker_device,
            reranker_local_files_only=not args.allow_reranker_download,
            reranker_batch_size=args.reranker_batch_size,
            selected_depth=args.selected_depth,
            output_dir=args.output_dir,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"DS-06: ERROR\n- {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
