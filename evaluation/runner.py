"""Offline golden-dataset runner and a dependency-free demo entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping, Sequence

from langchain_core.documents import Document

from evaluation.adapters import (
    AnswerAdapter,
    FakeAnswerAdapter,
    FakeRetrievalAdapter,
    RetrievalAdapter,
    RetrieverAdapter,
)
from evaluation.integration import (
    build_deterministic_bm25_retriever,
    build_deterministic_hybrid_retriever,
    build_deterministic_retriever,
)
from evaluation.fingerprints import file_sha256, text_corpus_sha256
from evaluation.metrics import (
    first_relevant_rank,
    hit_at_k,
    keyword_coverage,
    mean_defined,
    no_answer_retrieval_accuracy,
    precision_at_k,
    recall_at_k,
    reciprocal_rank_at_k,
    refusal_accuracy,
)
from evaluation.models import (
    AnswerResult,
    CaseEvaluation,
    EvaluationReport,
    GoldenCase,
    RetrievedDocument,
)


def load_golden_dataset(path: str | Path) -> list[GoldenCase]:
    """Load strict JSONL cases and reject blank IDs or duplicates."""

    dataset_path = Path(path)
    if not dataset_path.is_file():
        raise FileNotFoundError(f"黄金评估集不存在: {dataset_path}")
    cases: list[GoldenCase] = []
    seen_ids: set[str] = set()
    for line_number, raw_line in enumerate(
        dataset_path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"黄金评估集第 {line_number} 行不是有效 JSON") from exc
        case = GoldenCase.from_dict(payload)
        if case.id in seen_ids:
            raise ValueError(f"黄金评估集存在重复 id: {case.id}")
        seen_ids.add(case.id)
        cases.append(case)
    if not cases:
        raise ValueError("黄金评估集不能为空")
    return cases


class EvaluationRunner:
    """Run retrieval and optional answerability evaluation without Web/LLM coupling."""

    def __init__(
        self,
        retrieval_adapter: RetrievalAdapter,
        answer_adapter: AnswerAdapter | None = None,
        *,
        dataset_name: str = "golden-dataset",
        default_top_k: int = 3,
        metadata: Mapping[str, Any] | None = None,
    ):
        if default_top_k <= 0:
            raise ValueError("default_top_k 必须大于 0")
        self.retrieval_adapter = retrieval_adapter
        self.answer_adapter = answer_adapter
        self.dataset_name = dataset_name
        self.default_top_k = default_top_k
        self.metadata = dict(metadata or {})

    def run(self, cases: Sequence[GoldenCase]) -> EvaluationReport:
        if not cases:
            raise ValueError("评估用例不能为空")
        results: list[CaseEvaluation] = []
        for case in cases:
            results.append(self._run_case(case))
        metric_names = (
            "recall_at_k",
            "precision_at_k",
            "mrr_at_k",
            "top_k_hit_rate",
            "correct_document_avg_rank",
            "no_answer_retrieval_accuracy",
            "refusal_accuracy",
            "keyword_coverage",
        )
        metrics = {
            name: mean_defined([result.metrics.get(name) for result in results])
            for name in metric_names
        }
        metrics["successful_case_rate"] = sum(
            result.status == "success" for result in results
        ) / len(results)
        metrics["average_duration_ms"] = sum(
            result.duration_ms for result in results
        ) / len(results)
        category_metrics = {
            category: self._aggregate_results(
                [result for result in results if result.category == category],
                metric_names,
            )
            for category in sorted({result.category for result in results})
        }
        split_metrics = {
            split: self._aggregate_results(
                [result for result in results if result.split == split],
                metric_names,
            )
            for split in sorted({result.split for result in results})
        }
        return EvaluationReport(
            dataset_name=self.dataset_name,
            top_k=self.default_top_k,
            case_results=tuple(results),
            metrics=metrics,
            metadata=self.metadata,
            category_metrics=category_metrics,
            split_metrics=split_metrics,
        )

    @staticmethod
    def _aggregate_results(
        results: Sequence[CaseEvaluation],
        metric_names: Sequence[str],
    ) -> dict[str, float | None]:
        aggregate = {
            name: mean_defined([result.metrics.get(name) for result in results])
            for name in metric_names
        }
        aggregate["case_count"] = float(len(results))
        aggregate["successful_case_rate"] = (
            sum(result.status == "success" for result in results) / len(results)
        )
        aggregate["average_duration_ms"] = (
            sum(result.duration_ms for result in results) / len(results)
        )
        return aggregate

    def _run_case(self, case: GoldenCase) -> CaseEvaluation:
        top_k = case.top_k or self.default_top_k
        started = perf_counter()
        retrieved: list[RetrievedDocument] = []
        metrics: dict[str, float | None] = {
            "recall_at_k": None,
            "precision_at_k": None,
            "mrr_at_k": None,
            "top_k_hit_rate": None,
            "correct_document_avg_rank": None,
            "no_answer_retrieval_accuracy": None,
            "refusal_accuracy": None,
            "keyword_coverage": None,
        }
        answered: bool | None = None
        try:
            retrieved = list(self.retrieval_adapter.retrieve(case.question, top_k))
            document_ids = [document.document_id for document in retrieved]
            metrics.update(
                recall_at_k=recall_at_k(case.expected_document_ids, document_ids, top_k),
                precision_at_k=precision_at_k(case.expected_document_ids, document_ids, top_k),
                mrr_at_k=reciprocal_rank_at_k(case.expected_document_ids, document_ids, top_k),
                top_k_hit_rate=hit_at_k(case.expected_document_ids, document_ids, top_k),
                correct_document_avg_rank=first_relevant_rank(
                    case.expected_document_ids, document_ids, top_k
                ),
                no_answer_retrieval_accuracy=no_answer_retrieval_accuracy(
                    case.expected_document_ids, document_ids, top_k
                ),
            )
            if self.answer_adapter is not None:
                answer = self.answer_adapter.answer(case.question, retrieved)
                answered = answer.answered
                metrics["refusal_accuracy"] = refusal_accuracy(case.should_answer, answered)
                metrics["keyword_coverage"] = keyword_coverage(
                    case.expected_keywords, answer.text
                )
            status = "success"
            error_type = None
        except Exception as exc:
            status = "error"
            error_type = type(exc).__name__

        return CaseEvaluation(
            case_id=case.id,
            question=case.question,
            top_k=top_k,
            retrieved_document_ids=tuple(document.document_id for document in retrieved),
            retrieved_distances=tuple(document.distance for document in retrieved),
            metrics=metrics,
            duration_ms=(perf_counter() - started) * 1000,
            status=status,
            answered=answered,
            error_type=error_type,
            category=case.category,
            split=case.split,
        )


def _load_demo_documents(dataset_path: Path) -> list[Document]:
    documents_dir = dataset_path.parent / "documents"
    documents: list[Document] = []
    if not documents_dir.is_dir():
        return documents
    for path in sorted(documents_dir.glob("*.txt")):
        document_id = path.stem
        documents.append(
            Document(
                page_content=path.read_text(encoding="utf-8"),
                metadata={
                    "document_id": document_id,
                    "chunk_id": f"{document_id}:0",
                    "source_file": path.name,
                },
            )
        )
    return documents


def _build_demo_runner(
    cases: Sequence[GoldenCase],
    dataset_path: Path,
    retrieval_mode: str = "dense",
    *,
    rrf_k: int = 60,
    dense_weight: float = 1.0,
    lexical_weight: float = 1.0,
    candidate_multiplier: int = 5,
    lexical_score_threshold: float | None = None,
) -> EvaluationRunner:
    answer_mapping = {}
    for case in cases:
        answer_mapping[case.question] = AnswerResult(
            answered=case.should_answer,
            text=" ".join(case.expected_keywords) if case.should_answer else "",
        )
    documents = _load_demo_documents(dataset_path)
    metadata: dict[str, Any] = {
        "baseline_type": f"deterministic-{retrieval_mode}",
        "retrieval_mode": retrieval_mode,
        "document_count": len(documents),
        "embedding_provider": "evaluation-fake",
        "embedding_model": "sha256-token-hash-v1",
        "embedding_dimension": 64,
        "case_count": len(cases),
        "case_top_k_values": sorted({case.top_k for case in cases}),
        "score_threshold": None,
        "lexical_score_threshold": lexical_score_threshold,
        "dense_weight": dense_weight,
        "lexical_weight": lexical_weight,
        "rrf_k": rrf_k,
        "candidate_multiplier": candidate_multiplier,
        "dataset_sha256": file_sha256(dataset_path),
    }
    if documents:
        metadata["documents_sha256"] = text_corpus_sha256(dataset_path.parent / "documents")
        if retrieval_mode == "dense":
            retrieval_adapter = RetrieverAdapter(build_deterministic_retriever(documents))
        elif retrieval_mode == "bm25":
            retrieval_adapter = RetrieverAdapter(
                build_deterministic_bm25_retriever(documents),
                retrieval_method="retrieve_lexical",
                lexical_score_threshold=lexical_score_threshold,
            )
        elif retrieval_mode == "hybrid":
            retrieval_adapter = RetrieverAdapter(
                build_deterministic_hybrid_retriever(
                    documents,
                    rrf_k=rrf_k,
                    dense_weight=dense_weight,
                    lexical_weight=lexical_weight,
                    candidate_multiplier=candidate_multiplier,
                ),
                retrieval_method="retrieve_hybrid",
                lexical_score_threshold=lexical_score_threshold,
            )
        else:
            raise ValueError(f"不支持的 retrieval_mode: {retrieval_mode}")
    else:
        retrieval_mapping = {
            case.question: tuple(
                RetrievedDocument(
                    document_id=document_id,
                    content=" ".join(case.expected_keywords),
                    rank=index,
                )
                for index, document_id in enumerate(case.expected_document_ids, 1)
            )
            for case in cases
        }
        retrieval_adapter = FakeRetrievalAdapter(retrieval_mapping)
    return EvaluationRunner(
        retrieval_adapter,
        FakeAnswerAdapter(answer_mapping),
        dataset_name="demo-golden-dataset",
        metadata=metadata,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an offline RAG golden evaluation dataset")
    parser.add_argument(
        "--dataset",
        default="evaluation/datasets/golden_dataset.jsonl",
        help="JSONL golden dataset path",
    )
    parser.add_argument("--output-json", help="Write JSON report to this path")
    parser.add_argument("--output-markdown", help="Write Markdown report to this path")
    parser.add_argument(
        "--retrieval-mode",
        choices=("dense", "bm25", "hybrid"),
        default="dense",
        help="Deterministic retrieval strategy used by the offline smoke run",
    )
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--dense-weight", type=float, default=1.0)
    parser.add_argument("--lexical-weight", type=float, default=1.0)
    parser.add_argument("--candidate-multiplier", type=int, default=5)
    parser.add_argument("--lexical-score-threshold", type=float, default=None)
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    cases = load_golden_dataset(dataset_path)
    report = _build_demo_runner(
        cases,
        dataset_path,
        args.retrieval_mode,
        rrf_k=args.rrf_k,
        dense_weight=args.dense_weight,
        lexical_weight=args.lexical_weight,
        candidate_multiplier=args.candidate_multiplier,
        lexical_score_threshold=args.lexical_score_threshold,
    ).run(cases)
    if args.output_json:
        Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_json).write_text(report.to_json(), encoding="utf-8")
    if args.output_markdown:
        Path(args.output_markdown).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_markdown).write_text(report.to_markdown(), encoding="utf-8")
    print(report.to_markdown())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
