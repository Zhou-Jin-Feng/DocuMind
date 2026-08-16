"""文档生命周期的状态、稳定身份和跨层数据契约。"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


class LifecycleStatus(str, Enum):
    """索引从构建、激活到回收的持久化状态。"""
    PENDING = "pending"
    INDEXING = "indexing"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    FAILED = "failed"
    DELETING = "deleting"
    DELETED = "deleted"


class OperationStatus(str, Enum):
    """一次摄取或重建操作的执行状态。"""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


def stable_hash(*parts: str) -> str:
    """对带长度前缀的多个字段求哈希，避免直接拼接造成边界碰撞。"""
    digest = hashlib.sha256()
    for part in parts:
        encoded = part.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def normalize_display_name(value: str) -> str:
    """只保留文件名并做 Unicode NFKC 归一化，形成稳定的展示身份。"""
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
    """由租户、Collection 和规范化文件名生成逻辑文档身份。"""
    normalized = normalize_display_name(display_name).casefold()
    return stable_hash("document", tenant_id, collection_id, normalized)


def build_document_version_id(document_key: str, source_sha256: str) -> str:
    """由逻辑文档身份和源文件内容生成不可变版本身份。"""
    return stable_hash("document-version", document_key, source_sha256)


def build_index_id(document_version_id: str, index_fingerprint: str) -> str:
    """由内容版本和索引配置生成可复现的索引身份。"""
    return stable_hash("index", document_version_id, index_fingerprint)


@dataclass(frozen=True)
class IndexManifest:
    """影响 Chunk 或向量结果的配置快照，也是索引指纹的输入。"""
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
    """注册表对索引请求的裁决：构建、无操作或已有操作进行中。"""
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
class DocumentDeletionResult:
    status: str
    document_key: str
    deleted_index_count: int
    deleted_chunk_count: int
    collection_count: int
    cleanup_pending: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class IndexAuditReport:
    """SQLite 注册状态与 Milvus 实际库存之间的差异报告。"""
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
    """只描述重建将产生的变化，不修改注册表或向量数据。"""

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
