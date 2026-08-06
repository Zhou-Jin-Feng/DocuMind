"""Production-component wiring for generating a real retrieval baseline."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

from app.config import settings
from app.core.document_chunker import DocumentChunker
from app.core.embedding_client import UniversalEmbeddingClient
from app.core.retriever import Retriever
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
    if score_threshold is not None and score_threshold < 0:
        raise ValueError("score_threshold 不能小于 0")
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


def build_configured_retrieval_adapter(
    documents: Sequence[Document],
    *,
    provider: str | None = None,
    collection_name: str = "rag_evaluation",
    persist_directory: str = "./data/evaluation_chroma_db",
    score_threshold: float | None = None,
) -> tuple[RetrieverAdapter, IndexingSummary]:
    """Build a baseline adapter using the configured real Embedding provider."""

    if score_threshold is not None and score_threshold < 0:
        raise ValueError("score_threshold 不能小于 0")
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
