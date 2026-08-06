"""Deterministic local components for exercising the production Retriever."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.documents import Document

from app.core.retriever import Retriever


class DeterministicEmbeddingClient:
    """Small hash embedding used only by offline evaluation and integration tests."""

    provider = "evaluation-fake"
    model_name = "sha256-token-hash-v1"
    dimension = 64

    @classmethod
    def _tokens(cls, text: str) -> list[str]:
        normalized = (text or "").casefold()
        return re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", normalized)

    def embed_text(self, text: str) -> list[float]:
        tokens = self._tokens(text)
        if not tokens:
            raise ValueError("评估 Embedding 输入不能为空")
        vector = [0.0] * self.dimension
        for token in tokens:
            bucket = int.from_bytes(
                hashlib.sha256(token.encode("utf-8")).digest()[:4], "big"
            ) % self.dimension
            vector[bucket] += 1.0
        return vector

    def embed_texts_batch(
        self,
        texts: Sequence[str],
        *,
        show_progress: bool = False,
    ) -> list[list[float]]:
        del show_progress
        return [self.embed_text(text) for text in texts]


class InMemoryVectorStore:
    """Chroma-compatible search surface backed by deterministic local records."""

    def __init__(
        self,
        records: Sequence[tuple[Document, Sequence[float]]],
    ):
        self._records = tuple(
            (document, tuple(float(value) for value in embedding))
            for document, embedding in records
        )
        dimensions = {len(embedding) for _, embedding in self._records}
        if len(dimensions) > 1:
            raise ValueError("评估向量维度必须一致")

    @staticmethod
    def _matches_where(metadata: Mapping[str, Any], where: Mapping[str, Any] | None) -> bool:
        return not where or all(metadata.get(key) == value for key, value in where.items())

    def search(
        self,
        query_embedding: Sequence[float],
        n_results: int = 5,
        where: Mapping[str, Any] | None = None,
    ) -> dict[str, list[Any]]:
        if not query_embedding:
            raise ValueError("评估查询向量不能为空")
        if n_results <= 0:
            raise ValueError("n_results 必须大于 0")
        candidates = [
            (document, embedding)
            for document, embedding in self._records
            if self._matches_where(document.metadata, where)
        ]
        ranked = sorted(
            candidates,
            key=lambda item: sum(
                (left - right) ** 2 for left, right in zip(query_embedding, item[1])
            ),
        )[:n_results]
        return {
            "ids": [str(document.metadata.get("chunk_id", index)) for index, (document, _) in enumerate(ranked)],
            "documents": [document.page_content for document, _ in ranked],
            "metadatas": [dict(document.metadata) for document, _ in ranked],
            "distances": [
                sum((left - right) ** 2 for left, right in zip(query_embedding, embedding))
                for document, embedding in ranked
            ],
        }


def build_deterministic_retriever(documents: Sequence[Document]) -> Retriever:
    """Build the production Retriever with deterministic local dependencies."""

    embedding_client = DeterministicEmbeddingClient()
    records = [
        (document, embedding_client.embed_text(document.page_content))
        for document in documents
    ]
    return Retriever(InMemoryVectorStore(records), embedding_client)
