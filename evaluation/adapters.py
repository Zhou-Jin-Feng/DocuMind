"""Adapters that keep evaluation independent from production providers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from evaluation.models import AnswerResult, RetrievedDocument


class RetrievalAdapter(Protocol):
    """Protocol implemented by real and fake retrieval backends."""

    def retrieve(self, question: str, top_k: int) -> Sequence[RetrievedDocument]:
        ...


class AnswerAdapter(Protocol):
    """Protocol for optional answerability/refusal evaluation."""

    def answer(
        self,
        question: str,
        retrieved_documents: Sequence[RetrievedDocument],
    ) -> AnswerResult:
        ...


class RetrieverAdapter:
    """Bridge the production ``Retriever`` to the offline runner."""

    def __init__(self, retriever: Any):
        self.retriever = retriever

    def retrieve(self, question: str, top_k: int) -> Sequence[RetrievedDocument]:
        results = self.retriever.retrieve_semantic(question, top_k=top_k)
        documents: list[RetrievedDocument] = []
        for rank, result in enumerate(results, 1):
            metadata = dict(getattr(result, "metadata", {}) or {})
            document_id = str(metadata.get("document_id") or "")
            if not document_id:
                raise ValueError("真实检索结果缺少 metadata.document_id")
            documents.append(
                RetrievedDocument(
                    document_id=document_id,
                    content=str(getattr(result, "content", "") or ""),
                    chunk_id=str(metadata.get("chunk_id") or ""),
                    rank=rank,
                    metadata=metadata,
                )
            )
        return documents


class FakeRetrievalAdapter:
    """Deterministic question-to-results mapping for offline tests and demos."""

    def __init__(
        self,
        results_by_question: Mapping[str, Sequence[RetrievedDocument]],
    ):
        self._results = {
            self._normalize(question): tuple(results)
            for question, results in results_by_question.items()
        }

    @staticmethod
    def _normalize(question: str) -> str:
        return " ".join((question or "").casefold().split())

    def retrieve(self, question: str, top_k: int) -> Sequence[RetrievedDocument]:
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")
        return self._results.get(self._normalize(question), ())[:top_k]


class FakeAnswerAdapter:
    """Deterministic answerability mapping; never calls an LLM."""

    def __init__(
        self,
        answers_by_question: Mapping[str, AnswerResult | bool],
    ):
        self._answers = {
            FakeRetrievalAdapter._normalize(question): (
                value if isinstance(value, AnswerResult) else AnswerResult(answered=value)
            )
            for question, value in answers_by_question.items()
        }

    def answer(
        self,
        question: str,
        retrieved_documents: Sequence[RetrievedDocument],
    ) -> AnswerResult:
        del retrieved_documents
        try:
            return self._answers[FakeRetrievalAdapter._normalize(question)]
        except KeyError as exc:
            raise KeyError(f"FakeAnswerAdapter 缺少问题映射: {question}") from exc
