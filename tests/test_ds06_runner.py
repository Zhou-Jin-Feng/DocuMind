import json
from pathlib import Path

from app.core.retriever import RetrievalResult
from evaluation.ds06_runner import (
    FrozenCase,
    Qrel,
    _case_metrics,
    build_decision,
    load_frozen_corpus,
    load_frozen_cases,
)

DATASET_ROOT = Path("evaluation/datasets/p2_retrieval_v2")


def _result(chunk_id: str, document_id: str = "doc") -> RetrievalResult:
    return RetrievalResult(
        content="content",
        metadata={"document_id": document_id, "chunk_id": chunk_id},
        distance=0.1,
        rank=1,
    )


def test_frozen_corpus_preserves_production_ids_and_hashes():
    corpus = load_frozen_corpus(DATASET_ROOT)
    assert corpus.document_count == 75
    assert corpus.chunk_count == 235
    assert len({str(chunk.metadata["chunk_id"]) for chunk in corpus.chunks}) == 235


def test_frozen_cases_require_ds05_and_keep_two_splits():
    validation = load_frozen_cases(DATASET_ROOT, split="validation")
    holdout = load_frozen_cases(DATASET_ROOT, split="holdout")
    assert len(validation) == 50
    assert len(holdout) == 50
    assert {case.case_id for case in validation}.isdisjoint(
        {case.case_id for case in holdout}
    )


def test_graded_metrics_use_direct_evidence_for_recall_and_all_grades_for_ndcg():
    case = FrozenCase(
        case_id="case",
        question="q",
        split="validation",
        category="exact_lexical",
        answerable=True,
        qrels=(Qrel("doc", "direct", 3), Qrel("doc", "context", 1)),
    )
    metrics = _case_metrics(case, [_result("context"), _result("direct")], 2)
    assert metrics["recall_at_k"] == 1.0
    assert metrics["mrr_at_k"] == 0.5
    assert 0.0 < metrics["ndcg_at_k"] < 1.0


def test_no_answer_is_not_treated_as_ranking_success():
    case = FrozenCase(
        case_id="case",
        question="q",
        split="validation",
        category="general",
        answerable=False,
        qrels=(),
    )
    metrics = _case_metrics(case, [_result("unrelated")], 3)
    assert metrics["recall_at_k"] is None
    assert metrics["mrr_at_k"] is None
    assert metrics["no_answer_empty_accuracy"] == 0.0


def test_decision_requires_strict_gain_and_respects_latency_gate():
    base = {
        "recall_at_k": 0.8,
        "mrr_at_k": 0.8,
        "ndcg_at_k": 0.8,
        "successful_case_rate": 1.0,
        "p95_duration_ms": 100.0,
    }
    same = {
        "recall_at_k": 0.8,
        "mrr_at_k": 0.8,
        "ndcg_at_k": 0.8,
        "successful_case_rate": 1.0,
        "p95_duration_ms": 100.0,
    }
    improved = {
        "recall_at_k": 0.9,
        "mrr_at_k": 0.9,
        "ndcg_at_k": 0.85,
        "successful_case_rate": 1.0,
        "p95_duration_ms": 120.0,
    }
    slow = {
        "recall_at_k": 0.9,
        "mrr_at_k": 0.9,
        "ndcg_at_k": 0.85,
        "successful_case_rate": 1.0,
        "p95_duration_ms": 250.0,
    }
    result = build_decision(
        {
            "dense": {"metrics": base},
            "bm25": {"metrics": same},
            "hybrid": {"metrics": improved},
            "rerank": {"metrics": slow},
        },
        selected_depth=5,
    )
    assert result["decision"] == "GO"
    assert result["selected_candidate"] == "hybrid"
    assert not result["candidates"]["hybrid"]["failures"]
    assert "p95 exceeds 2x dense" in result["candidates"]["rerank"]["failures"]
