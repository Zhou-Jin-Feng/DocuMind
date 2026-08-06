"""Offline RAG evaluation primitives and regression tooling."""

from evaluation.adapters import FakeAnswerAdapter, FakeRetrievalAdapter, RetrieverAdapter
from evaluation.models import (
    AnswerResult,
    CaseEvaluation,
    EvaluationReport,
    GoldenCase,
    RetrievedDocument,
)
from evaluation.regression import RegressionGate, RegressionResult

__all__ = [
    "AnswerResult",
    "CaseEvaluation",
    "EvaluationReport",
    "EvaluationRunner",
    "FakeAnswerAdapter",
    "FakeRetrievalAdapter",
    "GoldenCase",
    "RegressionGate",
    "RegressionResult",
    "RetrievedDocument",
    "RetrieverAdapter",
    "load_golden_dataset",
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
