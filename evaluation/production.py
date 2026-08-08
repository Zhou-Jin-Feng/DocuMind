"""Production-component wiring for generating a real retrieval baseline."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

from app.config import settings
from app.core.document_chunker import DocumentChunker
from app.core.embedding_client import UniversalEmbeddingClient
from app.core.retriever import BM25Retriever, HybridRetriever, Retriever
from app.core.vector_store import VectorStore
from evaluation.adapters import RetrieverAdapter


@dataclass(frozen=True)
class IndexingSummary:
    """Counts and vector dimension recorded alongside a retrieval baseline."""

    document_count: int
    chunk_count: int
    embedding_provider: str
    embedding_model: str
    embedding_dimension: int
    chunk_size: int
    chunk_overlap: int

    def to_dict(self) -> dict[str, int | str]:
        return {
            "document_count": self.document_count,
            "chunk_count": self.chunk_count,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "embedding_dimension": self.embedding_dimension,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
        }


def load_text_documents(directory: str | Path) -> list[Document]:
    """Load evaluation TXT fixtures with stable logical IDs from file stems."""

    root = Path(directory)
    if not root.is_dir():
        raise NotADirectoryError(f"评估文档目录不存在: {root}")
    documents: list[Document] = []
    for path in sorted(root.glob("*.txt")):
        document_id = path.stem
        documents.append(
            Document(
                page_content=path.read_text(encoding="utf-8"),
                metadata={
                    "document_id": document_id,
                    "chunk_id": f"{document_id}:source",
                    "source_file": path.name,
                },
            )
        )
    if not documents:
        raise ValueError(f"评估文档目录没有 TXT 文件: {root}")
    return documents


def build_indexed_retrieval_adapter(
    documents: Sequence[Document],
    embedding_client: Any,
    vector_store: Any,
    *,
    chunker: DocumentChunker | None = None,
    score_threshold: float | None = None,
) -> tuple[RetrieverAdapter, IndexingSummary]:
    """Index documents with production components and return an evaluation adapter."""

    if not documents:
        raise ValueError("评估索引文档不能为空")
    if score_threshold is not None and (
        not isfinite(score_threshold) or score_threshold < 0
    ):
        raise ValueError("score_threshold 必须是非负有限数")
    chunker = chunker or DocumentChunker(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    chunks = chunker.chunk_documents_recursive(list(documents))
    if not chunks:
        raise ValueError("评估索引分块结果不能为空")

    texts = [chunk.page_content for chunk in chunks]
    batch_method = getattr(embedding_client, "embed_texts_batch", None)
    if callable(batch_method):
        embeddings = batch_method(texts, show_progress=False)
    else:
        embeddings = [embedding_client.embed_text(text) for text in texts]
    if len(embeddings) != len(chunks):
        raise ValueError(
            f"评估 Embedding 数量({len(embeddings)})与分块数量({len(chunks)})不匹配"
        )
    if not embeddings or not embeddings[0]:
        raise ValueError("评估 Embedding 不能为空")
    dimension = len(embeddings[0])
    if any(len(embedding) != dimension for embedding in embeddings):
        raise ValueError("评估 Embedding 维度不一致")

    vector_store.add_documents(chunks, embeddings)
    embedding_config = getattr(embedding_client, "config", {}) or {}
    return (
        RetrieverAdapter(
            Retriever(vector_store, embedding_client),
            score_threshold=score_threshold,
        ),
        IndexingSummary(
            document_count=len(documents),
            chunk_count=len(chunks),
            embedding_provider=str(getattr(embedding_client, "provider", "unknown")),
            embedding_model=str(
                embedding_config.get("model")
                or getattr(embedding_client, "model_name", "unknown")
            ),
            embedding_dimension=dimension,
            chunk_size=chunker.chunk_size,
            chunk_overlap=chunker.chunk_overlap,
        ),
    )


def build_hybrid_indexed_retrieval_adapter(
    documents: Sequence[Document],
    embedding_client: Any,
    vector_store: Any,
    *,
    chunker: DocumentChunker | None = None,
    score_threshold: float | None = None,
    rrf_k: int = 60,
    dense_weight: float = 1.0,
    lexical_weight: float = 1.0,
    candidate_multiplier: int = 5,
    lexical_score_threshold: float | None = None,
) -> tuple[RetrieverAdapter, IndexingSummary]:
    """Index documents once and expose Dense + BM25 RRF retrieval for evaluation."""
    if lexical_score_threshold is not None and (
        not isfinite(lexical_score_threshold) or lexical_score_threshold < 0
    ):
        raise ValueError("lexical_score_threshold 必须是非负有限数")
    dense_adapter, summary = build_indexed_retrieval_adapter(
        documents,
        embedding_client,
        vector_store,
        chunker=chunker,
        score_threshold=score_threshold,
    )
    dense_retriever = dense_adapter.retriever
    lexical_chunker = chunker or DocumentChunker(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    lexical_documents = lexical_chunker.chunk_documents_recursive(list(documents))
    hybrid = HybridRetriever(
        dense_retriever,
        BM25Retriever(lexical_documents),
        rrf_k=rrf_k,
        dense_weight=dense_weight,
        lexical_weight=lexical_weight,
        candidate_multiplier=candidate_multiplier,
    )
    dense_adapter.retriever = hybrid
    dense_adapter.retrieval_method = "retrieve_hybrid"
    dense_adapter.lexical_score_threshold = lexical_score_threshold
    return dense_adapter, summary


def build_lexical_retrieval_adapter(
    documents: Sequence[Document],
    *,
    chunker: DocumentChunker | None = None,
    lexical_score_threshold: float | None = None,
) -> tuple[RetrieverAdapter, IndexingSummary]:
    """Build a production-tokenizer BM25-only evaluation adapter."""
    if not documents:
        raise ValueError("评估词法文档不能为空")
    chunker = chunker or DocumentChunker(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    chunks = chunker.chunk_documents_recursive(list(documents))
    if not chunks:
        raise ValueError("评估词法分块结果不能为空")
    return (
        RetrieverAdapter(
            BM25Retriever(chunks),
            retrieval_method="retrieve_lexical",
            lexical_score_threshold=lexical_score_threshold,
        ),
        IndexingSummary(
            document_count=len(documents),
            chunk_count=len(chunks),
            embedding_provider="none",
            embedding_model="none",
            embedding_dimension=0,
            chunk_size=chunker.chunk_size,
            chunk_overlap=chunker.chunk_overlap,
        ),
    )


def build_configured_retrieval_adapter(
    documents: Sequence[Document],
    *,
    provider: str | None = None,
    collection_name: str = "rag_evaluation",
    persist_directory: str = "./data/evaluation_chroma_db",
    score_threshold: float | None = None,
) -> tuple[RetrieverAdapter, IndexingSummary]:
    """Build a baseline adapter using the configured real Embedding provider."""

    if score_threshold is not None and (
        not isfinite(score_threshold) or score_threshold < 0
    ):
        raise ValueError("score_threshold 必须是非负有限数")
    embedding_client = UniversalEmbeddingClient(
        provider or settings.default_embedding_provider
    )
    vector_store = VectorStore(
        collection_name=collection_name,
        persist_directory=persist_directory,
    )
    return build_indexed_retrieval_adapter(
        documents,
        embedding_client,
        vector_store,
        score_threshold=score_threshold,
    )


def build_configured_hybrid_retrieval_adapter(
    documents: Sequence[Document],
    *,
    provider: str | None = None,
    collection_name: str = "rag_evaluation_hybrid",
    persist_directory: str = "./data/evaluation_hybrid_chroma_db",
    score_threshold: float | None = None,
    rrf_k: int = 60,
    dense_weight: float = 1.0,
    lexical_weight: float = 1.0,
    candidate_multiplier: int = 5,
    lexical_score_threshold: float | None = None,
) -> tuple[RetrieverAdapter, IndexingSummary]:
    """Build a real-provider Dense + BM25 RRF evaluation adapter."""
    embedding_client = UniversalEmbeddingClient(
        provider or settings.default_embedding_provider
    )
    vector_store = VectorStore(
        collection_name=collection_name,
        persist_directory=persist_directory,
    )
    return build_hybrid_indexed_retrieval_adapter(
        documents,
        embedding_client,
        vector_store,
        score_threshold=score_threshold,
        rrf_k=rrf_k,
        dense_weight=dense_weight,
        lexical_weight=lexical_weight,
        candidate_multiplier=candidate_multiplier,
        lexical_score_threshold=lexical_score_threshold,
    )
