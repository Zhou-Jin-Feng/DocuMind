"""Data contracts for document and index lifecycle management."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


class LifecycleStatus(str, Enum):
    PENDING = "pending"
    INDEXING = "indexing"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    FAILED = "failed"
    DELETING = "deleting"
    DELETED = "deleted"


class OperationStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


def stable_hash(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        encoded = part.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def normalize_display_name(value: str) -> str:
    name = Path(value).name.strip()
    if not name:
        raise ValueError("display_name cannot be empty")
    return unicodedata.normalize("NFKC", name)


def build_document_key(
    display_name: str,
    *,
    tenant_id: str,
    collection_id: str,
) -> str:
    normalized = normalize_display_name(display_name).casefold()
    return stable_hash("document", tenant_id, collection_id, normalized)


def build_document_version_id(document_key: str, source_sha256: str) -> str:
    return stable_hash("document-version", document_key, source_sha256)


def build_index_id(document_version_id: str, index_fingerprint: str) -> str:
    return stable_hash("index", document_version_id, index_fingerprint)


@dataclass(frozen=True)
class IndexManifest:
    schema_version: int
    parser: str
    chunker: str
    chunk_size: int
    chunk_overlap: int
    embedding_provider: str
    embedding_model: str
    embedding_dimension: int

    def __post_init__(self) -> None:
        if self.schema_version <= 0:
            raise ValueError("schema_version must be positive")
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if self.chunk_overlap < 0 or self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be between 0 and chunk_size")
        if self.embedding_dimension <= 0:
            raise ValueError("embedding_dimension must be positive")
        for value in (
            self.parser,
            self.chunker,
            self.embedding_provider,
            self.embedding_model,
        ):
            if not value.strip():
                raise ValueError("manifest string fields cannot be empty")

    def to_dict(self) -> dict[str, int | str]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @property
    def fingerprint(self) -> str:
        return stable_hash("index-manifest", self.to_json())

    @classmethod
    def from_json(cls, value: str) -> "IndexManifest":
        payload = json.loads(value)
        if not isinstance(payload, Mapping):
            raise TypeError("index manifest must be a JSON object")
        return cls(**dict(payload))


@dataclass(frozen=True)
class IndexClaim:
    action: str
    operation_id: str
    document_key: str
    document_version_id: str
    index_id: str
    previous_index_id: str | None

    @property
    def should_build(self) -> bool:
        return self.action == "build"


@dataclass(frozen=True)
class IngestionResult:
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class IndexAuditReport:
    active_index_ids: tuple[str, ...]
    stale_index_ids: tuple[str, ...]
    orphan_index_ids: tuple[str, ...]
    missing_active_index_ids: tuple[str, ...]
    legacy_chunk_count: int = 0
    mismatched_active_index_ids: tuple[str, ...] = ()

    @property
    def healthy(self) -> bool:
        return not (
            self.stale_index_ids
            or self.orphan_index_ids
            or self.missing_active_index_ids
            or self.mismatched_active_index_ids
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RebuildPlan:
    """Describe a document rebuild without changing registry or vectors."""

    status: str
    document_key: str
    display_name: str
    source_path: str
    current_index_id: str | None
    planned_index_id: str | None
    source_sha256: str | None
    reason: str
    current_index_fingerprint: str | None = None
    planned_index_fingerprint: str | None = None
    configuration_changed: bool = False
    target_index_id: str | None = None
    target_index_fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
