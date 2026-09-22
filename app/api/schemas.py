"""Public v1 HTTP contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RETRIEVE_SCHEMA_VERSION = "1.0"
RETRIEVAL_VERSION = "dense-v1"
RETRIEVE_MAX_REQUEST_SIZE_BYTES = 16 * 1024
_CONTENT_HASH_PATTERN = r"^[a-f0-9]{64}$"


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("question cannot be blank")
        return normalized


class RetrieveRequest(BaseModel):
    """Versioned single-document dense retrieval request."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "schema_version": RETRIEVE_SCHEMA_VERSION,
                    "query": "What evidence supports the claim?",
                    "document_key": "a" * 64,
                    "expected_index_id": "b" * 64,
                    "top_k": 3,
                    "retrieval_mode": "dense",
                    "distance_threshold": None,
                }
            ]
        },
    )

    schema_version: Literal["1.0"]
    query: str = Field(min_length=1, max_length=4000)
    document_key: str = Field(pattern=_CONTENT_HASH_PATTERN)
    expected_index_id: str = Field(pattern=_CONTENT_HASH_PATTERN)
    top_k: int = Field(ge=1, le=20)
    retrieval_mode: Literal["dense"]
    distance_threshold: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
    )

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query cannot be blank")
        return normalized


class RetrievalChunkResponse(BaseModel):
    """Whitelisted evidence fields for one retrieved source chunk."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(pattern=_CONTENT_HASH_PATTERN)
    content: str = Field(min_length=1)
    content_sha256: str = Field(pattern=_CONTENT_HASH_PATTERN)
    source: str = Field(min_length=1)
    page_number: int | None = Field(default=None, ge=1)
    distance: float = Field(ge=0, allow_inf_nan=False)
    rank: int = Field(ge=1, le=20)


class RetrieveResponse(BaseModel):
    """Versioned retrieval result with immutable document and index identity."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "schema_version": RETRIEVE_SCHEMA_VERSION,
                    "service_version": "3.1.0",
                    "retrieval_version": RETRIEVAL_VERSION,
                    "retrieval_mode": "dense",
                    "document_key": "a" * 64,
                    "index_id": "b" * 64,
                    "source_sha256": "c" * 64,
                    "chunks": [
                        {
                            "chunk_id": "d" * 64,
                            "content": "A retrieved evidence chunk.",
                            "content_sha256": "e" * 64,
                            "source": "paper.pdf",
                            "page_number": 3,
                            "distance": 0.42,
                            "rank": 1,
                        }
                    ],
                }
            ]
        },
    )

    schema_version: Literal["1.0"]
    service_version: str = Field(min_length=1)
    retrieval_version: Literal["dense-v1"]
    retrieval_mode: Literal["dense"]
    document_key: str = Field(pattern=_CONTENT_HASH_PATTERN)
    index_id: str = Field(pattern=_CONTENT_HASH_PATTERN)
    source_sha256: str = Field(pattern=_CONTENT_HASH_PATTERN)
    chunks: list[RetrievalChunkResponse] = Field(max_length=20)


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
    active_version_id: str | None = None
    version_count: int
    error_type: str | None = None
    created_at: str
    updated_at: str


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int


class DocumentIndexResponse(BaseModel):
    index_id: str
    document_version_id: str
    version_number: int
    status: str
    chunk_count: int
    error_type: str | None = None
    file_type: str
    file_size_bytes: int
    source_sha256: str
    created_at: str
    updated_at: str
    activated_at: str | None = None
    is_active: bool


class DocumentDetailResponse(DocumentResponse):
    indexes: list[DocumentIndexResponse]


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


class DocumentDeletionResponse(BaseModel):
    status: str
    document_key: str
    deleted_index_count: int
    deleted_chunk_count: int
    collection_count: int
    cleanup_pending: bool = False


class ComponentHealth(BaseModel):
    application: str
    milvus: str
    embedding: str
    llm: str
    registry: str
    retrieval: str


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
