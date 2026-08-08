"""Adapters that keep evaluation independent from production providers."""

from __future__ import annotations

import gc
from math import isfinite
from collections.abc import Mapping, Sequence
from typing import Any, Optional, Protocol

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

    def __init__(
        self,
        retriever: Any,
        score_threshold: Optional[float] = None,
        *,
        retrieval_method: str = "retrieve_semantic",
        lexical_score_threshold: Optional[float] = None,
    ):
        if score_threshold is not None and (
            not isfinite(score_threshold) or score_threshold < 0
        ):
            raise ValueError("score_threshold 必须是非负有限数")
        if lexical_score_threshold is not None and (
            not isfinite(lexical_score_threshold) or lexical_score_threshold < 0
        ):
            raise ValueError("lexical_score_threshold 必须是非负有限数")
        self.retriever = retriever
        self.score_threshold = score_threshold
        self.lexical_score_threshold = lexical_score_threshold
        if not isinstance(retrieval_method, str) or not callable(
            getattr(retriever, retrieval_method, None)
        ):
            raise ValueError(f"retrieval_method 不可调用: {retrieval_method}")
        self.retrieval_method = retrieval_method

    def retrieve(self, question: str, top_k: int) -> Sequence[RetrievedDocument]:
        retrieval_kwargs = {"top_k": top_k}
        if self.score_threshold is not None and self.retrieval_method != "retrieve_lexical":
            retrieval_kwargs["score_threshold"] = self.score_threshold
        if self.lexical_score_threshold is not None and self.retrieval_method in {
            "retrieve_lexical",
            "retrieve_hybrid",
        }:
            retrieval_kwargs["lexical_score_threshold"] = self.lexical_score_threshold
        method = getattr(self.retriever, self.retrieval_method)
        results = method(question, **retrieval_kwargs)
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
                    distance=getattr(result, "distance", None),
                    lexical_score=getattr(result, "lexical_score", None),
                    fusion_score=getattr(result, "fusion_score", None),
                    query_fusion_score=getattr(result, "query_fusion_score", None),
                    rerank_score=getattr(result, "rerank_score", None),
                )
            )
        return documents

    def close(self) -> None:
        """Release Chroma/client references before deleting a temporary baseline store."""

        retriever = self.retriever
        self.retriever = None
        self.score_threshold = None
        self.lexical_score_threshold = None
        self.retrieval_method = "retrieve_semantic"
        if retriever is not None:
            current = retriever
            wrappers: list[Any] = []
            seen: set[int] = set()
            while current is not None and id(current) not in seen:
                seen.add(id(current))
                wrappers.append(current)
                if hasattr(current, "base_retriever"):
                    current = current.base_retriever
                elif hasattr(current, "dense_retriever"):
                    current = current.dense_retriever
                else:
                    break
            dense_retriever = current
            vector_store = getattr(dense_retriever, "vector_store", None)
            if hasattr(dense_retriever, "vector_store"):
                dense_retriever.vector_store = None
            if hasattr(dense_retriever, "embedding_client"):
                dense_retriever.embedding_client = None
            if vector_store is not None:
                if hasattr(vector_store, "collection"):
                    vector_store.collection = None
                if hasattr(vector_store, "client"):
                    vector_store.client = None
            for wrapper in wrappers:
                reranker = getattr(wrapper, "reranker", None)
                close = getattr(reranker, "close", None)
                if callable(close):
                    close()
                if hasattr(wrapper, "base_retriever"):
                    wrapper.base_retriever = None
        gc.collect()

    def __enter__(self) -> "RetrieverAdapter":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


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
