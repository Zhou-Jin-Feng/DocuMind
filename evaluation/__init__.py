"""Offline RAG evaluation primitives and regression tooling."""

from evaluation.adapters import (
    FakeAnswerAdapter,
    FakeRetrievalAdapter,
    RetrieverAdapter,
)
from evaluation.comparison import EvaluationComparison, build_evaluation_comparison
from evaluation.models import (
    AnswerResult,
    CaseEvaluation,
    EvaluationReport,
    GoldenCase,
    RetrievedDocument,
)
from evaluation.regression import (
    EvaluationSnapshot,
    RegressionGate,
    RegressionResult,
    load_evaluation_snapshot,
    report_compatibility_issues,
)
from evaluation.integration import (
    DeterministicEmbeddingClient,
    InMemoryVectorStore,
    build_deterministic_bm25_retriever,
    build_deterministic_hybrid_retriever,
    build_deterministic_retriever,
)
from evaluation.production import (
    IndexingSummary,
    build_configured_hybrid_retrieval_adapter,
    build_configured_retrieval_adapter,
    build_indexed_retrieval_adapter,
    build_hybrid_indexed_retrieval_adapter,
    build_lexical_retrieval_adapter,
    enhance_retrieval_adapter,
    load_text_documents,
)

__all__ = [
    "AnswerResult",
    "CaseEvaluation",
    "EvaluationReport",
    "EvaluationComparison",
    "EvaluationSnapshot",
    "EvaluationRunner",
    "FakeAnswerAdapter",
    "FakeRetrievalAdapter",
    "DeterministicEmbeddingClient",
    "GoldenCase",
    "RegressionGate",
    "RegressionResult",
    "RetrievedDocument",
    "RetrieverAdapter",
    "InMemoryVectorStore",
    "IndexingSummary",
    "build_deterministic_retriever",
    "build_evaluation_comparison",
    "build_deterministic_bm25_retriever",
    "build_deterministic_hybrid_retriever",
    "build_configured_retrieval_adapter",
    "build_configured_hybrid_retrieval_adapter",
    "build_indexed_retrieval_adapter",
    "build_hybrid_indexed_retrieval_adapter",
    "build_lexical_retrieval_adapter",
    "enhance_retrieval_adapter",
    "load_text_documents",
    "load_golden_dataset",
    "load_evaluation_snapshot",
    "report_compatibility_issues",
]


def __getattr__(name: str):
    """Lazy-load runner symbols so ``python -m evaluation.runner`` stays quiet."""

    if name in {"EvaluationRunner", "load_golden_dataset"}:
        from evaluation.runner import EvaluationRunner, load_golden_dataset

        return {
            "EvaluationRunner": EvaluationRunner,
            "load_golden_dataset": load_golden_dataset,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
