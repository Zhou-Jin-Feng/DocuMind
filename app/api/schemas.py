"""Public v1 HTTP contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("question cannot be blank")
        return normalized


class SourceResponse(BaseModel):
    rank: int
    source: str
    page_number: int | None = None
    excerpt: str
    distance: float | None = None
    lexical_score: float | None = None
    fusion_score: float | None = None
    rerank_score: float | None = None
    chunk_id: str | None = None


class DocumentResponse(BaseModel):
    document_key: str
    display_name: str
    status: str
    chunk_count: int
    file_type: str | None = None
    file_size_bytes: int | None = None
    active_index_id: str | None = None
    created_at: str
    updated_at: str


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int


class IngestionResponse(BaseModel):
    status: str
    operation_id: str
    document_key: str
    document_version_id: str
    index_id: str
    source_sha256: str
    chunk_count: int
    collection_count: int
    previous_index_id: str | None = None
    cleanup_pending: bool = False


class ComponentHealth(BaseModel):
    application: str
    milvus: str
    embedding: str
    llm: str
    registry: str


class HealthResponse(BaseModel):
    status: Literal["alive", "ready", "degraded"]
    version: str
    ready: bool
    components: ComponentHealth | None = None
    error_type: str | None = None


class PublicConfigResponse(BaseModel):
    embedding_provider: str
    embedding_model: str
    llm_provider: str
    collection_name: str
    allowed_extensions: list[str]
    max_upload_size_mb: int
    retrieval_top_k: int


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None
    fields: list[dict[str, str]] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
