"""文档、版本、索引与操作状态的 SQLite 权威注册表。"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from app.lifecycle.models import (
    IndexClaim,
    IndexManifest,
    LifecycleStatus,
    OperationStatus,
    stable_hash,
)

SCHEMA_VERSION = 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class DocumentRegistry:
    """
    在向量库之外持久化生命周期状态。

    写操作使用 ``BEGIN IMMEDIATE`` 串行化状态切换，使多个请求不能同时认领
    同一索引；Milvus 只保存检索数据，不负责判断哪个索引版本对外可见。
    """

    def __init__(self, database_path: str):
        self.database_path = str(Path(database_path))
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._transaction() as connection:
            current_version = connection.execute("PRAGMA user_version").fetchone()[0]
            if current_version not in (0, SCHEMA_VERSION):
                raise RuntimeError(
                    f"Unsupported document registry schema: {current_version}"
                )
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    document_key TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    collection_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    active_index_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS document_versions (
                    document_version_id TEXT PRIMARY KEY,
                    document_key TEXT NOT NULL REFERENCES documents(document_key),
                    source_sha256 TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    file_size_bytes INTEGER NOT NULL CHECK(file_size_bytes >= 0),
                    created_at TEXT NOT NULL,
                    UNIQUE(document_key, source_sha256)
                );

                CREATE TABLE IF NOT EXISTS document_indexes (
                    index_id TEXT PRIMARY KEY,
                    document_version_id TEXT NOT NULL
                        REFERENCES document_versions(document_version_id),
                    index_fingerprint TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    chunk_count INTEGER NOT NULL DEFAULT 0 CHECK(chunk_count >= 0),
                    error_type TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    activated_at TEXT,
                    UNIQUE(document_version_id, index_fingerprint)
                );

                CREATE TABLE IF NOT EXISTS index_operations (
                    operation_id TEXT PRIMARY KEY,
                    index_id TEXT NOT NULL REFERENCES document_indexes(index_id),
                    operation_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    chunks_total INTEGER NOT NULL DEFAULT 0 CHECK(chunks_total >= 0),
                    chunks_indexed INTEGER NOT NULL DEFAULT 0 CHECK(chunks_indexed >= 0),
                    error_type TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_documents_scope
                    ON documents(tenant_id, collection_id);
                CREATE INDEX IF NOT EXISTS idx_versions_document
                    ON document_versions(document_key);
                CREATE INDEX IF NOT EXISTS idx_indexes_version
                    ON document_indexes(document_version_id);
                CREATE INDEX IF NOT EXISTS idx_indexes_status
                    ON document_indexes(status);
                """)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def claim_index(
        self,
        *,
        document_key: str,
        document_version_id: str,
        index_id: str,
        tenant_id: str,
        collection_id: str,
        display_name: str,
        source_sha256: str,
        source_path: str,
        file_type: str,
        file_size_bytes: int,
        manifest: IndexManifest,
        operation_type: str = "ingest",
        force: bool = False,
    ) -> IndexClaim:
        """
        原子认领一次索引操作，并返回 ``build``、``noop`` 或 ``in_progress``。

        身份相同且已激活时默认 no-op；强制重建只重新打开操作，不会提前
        清除当前活动索引，因此失败时仍可继续检索旧版本。
        """
        now = _utc_now()
        operation_id = stable_hash(operation_type, index_id)
        with self._transaction() as connection:
            existing_document = connection.execute(
                "SELECT active_index_id FROM documents WHERE document_key=?",
                (document_key,),
            ).fetchone()
            if (
                existing_document is not None
                and existing_document["active_index_id"] is None
            ):
                deleting = connection.execute(
                    """
                    SELECT 1
                    FROM document_indexes i
                    JOIN document_versions v
                      ON v.document_version_id=i.document_version_id
                    WHERE v.document_key=? AND i.status=?
                    LIMIT 1
                    """,
                    (document_key, LifecycleStatus.DELETING.value),
                ).fetchone()
                if deleting is not None:
                    return IndexClaim(
                        action="in_progress",
                        operation_id=operation_id,
                        document_key=document_key,
                        document_version_id=document_version_id,
                        index_id=index_id,
                        previous_index_id=None,
                    )

            connection.execute(
                """
                INSERT INTO documents(
                    document_key, tenant_id, collection_id, display_name,
                    active_index_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, NULL, ?, ?)
                ON CONFLICT(document_key) DO UPDATE SET
                    display_name=excluded.display_name,
                    updated_at=excluded.updated_at
                """,
                (
                    document_key,
                    tenant_id,
                    collection_id,
                    display_name,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO document_versions(
                    document_version_id, document_key, source_sha256,
                    source_path, file_type, file_size_bytes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_version_id) DO UPDATE SET
                    source_path=excluded.source_path,
                    file_size_bytes=excluded.file_size_bytes
                """,
                (
                    document_version_id,
                    document_key,
                    source_sha256,
                    source_path,
                    file_type,
                    file_size_bytes,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO document_indexes(
                    index_id, document_version_id, index_fingerprint,
                    manifest_json, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(index_id) DO NOTHING
                """,
                (
                    index_id,
                    document_version_id,
                    manifest.fingerprint,
                    manifest.to_json(),
                    LifecycleStatus.PENDING.value,
                    now,
                    now,
                ),
            )

            document = connection.execute(
                "SELECT active_index_id FROM documents WHERE document_key = ?",
                (document_key,),
            ).fetchone()
            index_row = connection.execute(
                "SELECT status FROM document_indexes WHERE index_id = ?",
                (index_id,),
            ).fetchone()
            previous_index_id = document["active_index_id"]
            if (
                previous_index_id == index_id
                and index_row["status"] == LifecycleStatus.ACTIVE.value
                and not force
            ):
                return IndexClaim(
                    action="noop",
                    operation_id=operation_id,
                    document_key=document_key,
                    document_version_id=document_version_id,
                    index_id=index_id,
                    previous_index_id=previous_index_id,
                )
            if index_row["status"] == LifecycleStatus.INDEXING.value:
                return IndexClaim(
                    action="in_progress",
                    operation_id=operation_id,
                    document_key=document_key,
                    document_version_id=document_version_id,
                    index_id=index_id,
                    previous_index_id=previous_index_id,
                )

            connection.execute(
                """
                UPDATE document_indexes
                SET status=?, error_type=NULL, updated_at=?
                WHERE index_id=?
                """,
                (LifecycleStatus.INDEXING.value, now, index_id),
            )
            connection.execute(
                """
                INSERT INTO index_operations(
                    operation_id, index_id, operation_type, status,
                    chunks_total, chunks_indexed, error_type,
                    created_at, updated_at, completed_at
                ) VALUES (?, ?, ?, ?, 0, 0, NULL, ?, ?, NULL)
                ON CONFLICT(operation_id) DO UPDATE SET
                    status=excluded.status,
                    chunks_total=0,
                    chunks_indexed=0,
                    error_type=NULL,
                    updated_at=excluded.updated_at,
                    completed_at=NULL
                """,
                (
                    operation_id,
                    index_id,
                    operation_type,
                    OperationStatus.RUNNING.value,
                    now,
                    now,
                ),
            )
            return IndexClaim(
                action="build",
                operation_id=operation_id,
                document_key=document_key,
                document_version_id=document_version_id,
                index_id=index_id,
                previous_index_id=previous_index_id,
            )

    def update_progress(
        self,
        operation_id: str,
        *,
        chunks_total: int,
        chunks_indexed: int,
    ) -> None:
        if chunks_total < 0 or chunks_indexed < 0 or chunks_indexed > chunks_total:
            raise ValueError("invalid indexing progress")
        with self._transaction() as connection:
            connection.execute(
                """
                UPDATE index_operations
                SET chunks_total=?, chunks_indexed=?, updated_at=?
                WHERE operation_id=?
                """,
                (chunks_total, chunks_indexed, _utc_now(), operation_id),
            )

    def activate_index(
        self,
        *,
        document_key: str,
        index_id: str,
        operation_id: str,
        chunk_count: int,
    ) -> str | None:
        """
        原子激活已完整写入的索引，并把旧活动索引标记为 superseded。

        返回旧索引 ID 供调用方在事务提交后清理 Milvus 数据；数据库事务内
        不执行网络 I/O，避免外部服务延迟长期占用 SQLite 写锁。
        """
        if chunk_count < 0:
            raise ValueError("chunk_count cannot be negative")
        now = _utc_now()
        with self._transaction() as connection:
            document = connection.execute(
                "SELECT active_index_id FROM documents WHERE document_key=?",
                (document_key,),
            ).fetchone()
            if document is None:
                raise KeyError(f"Unknown document: {document_key}")
            index = connection.execute(
                """
                SELECT i.status, v.document_key
                FROM document_indexes i
                JOIN document_versions v
                  ON v.document_version_id=i.document_version_id
                WHERE i.index_id=?
                """,
                (index_id,),
            ).fetchone()
            if index is None:
                raise KeyError(f"Unknown index: {index_id}")
            if index["document_key"] != document_key:
                raise ValueError(
                    f"Index {index_id} does not belong to document {document_key}"
                )
            if index["status"] != LifecycleStatus.INDEXING.value:
                raise ValueError(
                    f"Index is not ready for activation: {index_id} "
                    f"({index['status']})"
                )
            operation = connection.execute(
                "SELECT index_id, status FROM index_operations WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if operation is None:
                raise KeyError(f"Unknown index operation: {operation_id}")
            if operation["index_id"] != index_id:
                raise ValueError(
                    f"Operation {operation_id} does not belong to index {index_id}"
                )
            if operation["status"] != OperationStatus.RUNNING.value:
                raise ValueError(
                    f"Index operation is not running: {operation_id} "
                    f"({operation['status']})"
                )
            previous_index_id = document["active_index_id"]
            if previous_index_id and previous_index_id != index_id:
                connection.execute(
                    """
                    UPDATE document_indexes
                    SET status=?, updated_at=?
                    WHERE index_id=?
                    """,
                    (LifecycleStatus.SUPERSEDED.value, now, previous_index_id),
                )
            activated = connection.execute(
                """
                UPDATE document_indexes
                SET status=?, chunk_count=?, error_type=NULL,
                    updated_at=?, activated_at=?
                WHERE index_id=? AND status=?
                """,
                (
                    LifecycleStatus.ACTIVE.value,
                    chunk_count,
                    now,
                    now,
                    index_id,
                    LifecycleStatus.INDEXING.value,
                ),
            )
            if activated.rowcount != 1:
                raise RuntimeError(f"Failed to activate index: {index_id}")
            updated_document = connection.execute(
                """
                UPDATE documents
                SET active_index_id=?, updated_at=?
                WHERE document_key=?
                """,
                (index_id, now, document_key),
            )
            if updated_document.rowcount != 1:
                raise RuntimeError(f"Failed to update document: {document_key}")
            completed = connection.execute(
                """
                UPDATE index_operations
                SET status=?, chunks_total=?, chunks_indexed=?,
                    error_type=NULL, updated_at=?, completed_at=?
                WHERE operation_id=? AND status=?
                """,
                (
                    OperationStatus.COMPLETED.value,
                    chunk_count,
                    chunk_count,
                    now,
                    now,
                    operation_id,
                    OperationStatus.RUNNING.value,
                ),
            )
            if completed.rowcount != 1:
                raise RuntimeError(f"Failed to complete operation: {operation_id}")
            return previous_index_id

    def fail_index(self, index_id: str, operation_id: str, error_type: str) -> None:
        """记录构建失败；若目标原本就是活动索引，则恢复其可见状态。"""
        now = _utc_now()
        with self._transaction() as connection:
            active = connection.execute(
                "SELECT 1 FROM documents WHERE active_index_id=?",
                (index_id,),
            ).fetchone()
            if active is None:
                connection.execute(
                    """
                    UPDATE document_indexes
                    SET status=?, error_type=?, updated_at=?
                    WHERE index_id=?
                    """,
                    (LifecycleStatus.FAILED.value, error_type, now, index_id),
                )
            else:
                # A forced rebuild may temporarily mark the active index as
                # indexing. Preserve that active version if the rebuild fails.
                connection.execute(
                    """
                    UPDATE document_indexes
                    SET status=?, error_type=NULL, updated_at=?
                    WHERE index_id=?
                    """,
                    (LifecycleStatus.ACTIVE.value, now, index_id),
                )
            connection.execute(
                """
                UPDATE index_operations
                SET status=?, error_type=?, updated_at=?, completed_at=?
                WHERE operation_id=?
                """,
                (
                    OperationStatus.FAILED.value,
                    error_type,
                    now,
                    now,
                    operation_id,
                ),
            )

    def claim_document_deletion(
        self,
        document_key: str,
        *,
        tenant_id: str,
        collection_id: str,
    ) -> tuple[str, ...]:
        """先隐藏文档并认领其全部索引，返回需要从 Milvus 删除的 ID。"""
        now = _utc_now()
        with self._transaction() as connection:
            document = connection.execute(
                """
                SELECT document_key
                FROM documents
                WHERE document_key=? AND tenant_id=? AND collection_id=?
                """,
                (document_key, tenant_id, collection_id),
            ).fetchone()
            if document is None:
                raise KeyError(f"Unknown document in the current scope: {document_key}")

            indexes = connection.execute(
                """
                SELECT i.index_id, i.status
                FROM document_indexes i
                JOIN document_versions v
                  ON v.document_version_id=i.document_version_id
                WHERE v.document_key=?
                ORDER BY i.created_at, i.index_id
                """,
                (document_key,),
            ).fetchall()
            if any(
                index["status"] == LifecycleStatus.INDEXING.value for index in indexes
            ):
                raise ValueError(
                    f"Document index operation is in progress: {document_key}"
                )

            connection.execute(
                """
                UPDATE documents
                SET active_index_id=NULL, updated_at=?
                WHERE document_key=?
                """,
                (now, document_key),
            )
            connection.execute(
                """
                UPDATE document_indexes
                SET status=?, error_type=NULL, updated_at=?
                WHERE document_version_id IN (
                    SELECT document_version_id
                    FROM document_versions
                    WHERE document_key=?
                ) AND status<>?
                """,
                (
                    LifecycleStatus.DELETING.value,
                    now,
                    document_key,
                    LifecycleStatus.DELETED.value,
                ),
            )
            index_ids = tuple(str(index["index_id"]) for index in indexes)
            return index_ids

    def finalize_document_deletion(
        self,
        document_key: str,
        *,
        tenant_id: str,
        collection_id: str,
    ) -> tuple[str, ...]:
        """仅在向量删除完成后移除注册历史，并返回不再被引用的源文件。"""
        with self._transaction() as connection:
            document = connection.execute(
                """
                SELECT document_key
                FROM documents
                WHERE document_key=? AND tenant_id=? AND collection_id=?
                """,
                (document_key, tenant_id, collection_id),
            ).fetchone()
            if document is None:
                raise KeyError(f"Unknown document in the current scope: {document_key}")

            indexes = connection.execute(
                """
                SELECT i.status
                FROM document_indexes i
                JOIN document_versions v
                  ON v.document_version_id=i.document_version_id
                WHERE v.document_key=?
                """,
                (document_key,),
            ).fetchall()
            allowed_statuses = {
                LifecycleStatus.DELETING.value,
                LifecycleStatus.DELETED.value,
            }
            if any(index["status"] not in allowed_statuses for index in indexes):
                raise ValueError(f"Document deletion was not claimed: {document_key}")

            source_rows = connection.execute(
                """
                SELECT DISTINCT source_path
                FROM document_versions
                WHERE document_key=?
                """,
                (document_key,),
            ).fetchall()
            source_paths = tuple(str(row["source_path"]) for row in source_rows)
            connection.execute(
                """
                DELETE FROM index_operations
                WHERE index_id IN (
                    SELECT i.index_id
                    FROM document_indexes i
                    JOIN document_versions v
                      ON v.document_version_id=i.document_version_id
                    WHERE v.document_key=?
                )
                """,
                (document_key,),
            )
            connection.execute(
                """
                DELETE FROM document_indexes
                WHERE document_version_id IN (
                    SELECT document_version_id
                    FROM document_versions
                    WHERE document_key=?
                )
                """,
                (document_key,),
            )
            connection.execute(
                "DELETE FROM document_versions WHERE document_key=?",
                (document_key,),
            )
            deleted = connection.execute(
                "DELETE FROM documents WHERE document_key=?",
                (document_key,),
            )
            if deleted.rowcount != 1:
                raise RuntimeError(f"Failed to delete document: {document_key}")

            unreferenced_paths = []
            for source_path in source_paths:
                reference = connection.execute(
                    "SELECT 1 FROM document_versions WHERE source_path=? LIMIT 1",
                    (source_path,),
                ).fetchone()
                if reference is None:
                    unreferenced_paths.append(source_path)
            return tuple(sorted(unreferenced_paths))

    def mark_index_deleting(self, index_id: str) -> None:
        """认领非活动索引的可恢复删除；活动索引永远不能在此路径删除。"""
        with self._transaction() as connection:
            index = connection.execute(
                "SELECT status FROM document_indexes WHERE index_id=?",
                (index_id,),
            ).fetchone()
            if index is None:
                raise KeyError(f"Unknown index: {index_id}")
            active = connection.execute(
                "SELECT 1 FROM documents WHERE active_index_id=?",
                (index_id,),
            ).fetchone()
            if active is not None or index["status"] == LifecycleStatus.ACTIVE.value:
                raise ValueError(f"Cannot delete active index: {index_id}")
            allowed = {
                LifecycleStatus.SUPERSEDED.value,
                LifecycleStatus.FAILED.value,
                LifecycleStatus.DELETING.value,
                LifecycleStatus.DELETED.value,
            }
            if index["status"] not in allowed:
                raise ValueError(
                    f"Index is not eligible for deletion: {index_id} "
                    f"({index['status']})"
                )
            connection.execute(
                """
                UPDATE document_indexes
                SET status=?, updated_at=?
                WHERE index_id=?
                """,
                (LifecycleStatus.DELETING.value, _utc_now(), index_id),
            )

    def mark_index_deleted(self, index_id: str) -> None:
        """只有已被认领为 deleting 的索引才能进入 deleted。"""
        with self._transaction() as connection:
            index = connection.execute(
                "SELECT status FROM document_indexes WHERE index_id=?",
                (index_id,),
            ).fetchone()
            if index is None:
                raise KeyError(f"Unknown index: {index_id}")
            if index["status"] == LifecycleStatus.DELETED.value:
                return
            if index["status"] != LifecycleStatus.DELETING.value:
                raise ValueError(
                    f"Index deletion was not claimed: {index_id} ({index['status']})"
                )
            updated = connection.execute(
                """
                UPDATE document_indexes
                SET status=?, updated_at=?
                WHERE index_id=? AND status=?
                """,
                (
                    LifecycleStatus.DELETED.value,
                    _utc_now(),
                    index_id,
                    LifecycleStatus.DELETING.value,
                ),
            )
            if updated.rowcount != 1:
                raise RuntimeError(f"Failed to mark index deleted: {index_id}")

    def reset_index_for_retry(self, index_id: str) -> None:
        """释放中断的 indexing 认领，为显式重试恢复可进入构建的状态。"""
        now = _utc_now()
        with self._transaction() as connection:
            index = connection.execute(
                "SELECT status FROM document_indexes WHERE index_id=?",
                (index_id,),
            ).fetchone()
            if index is None:
                raise KeyError(f"Unknown index: {index_id}")
            if index["status"] != LifecycleStatus.INDEXING.value:
                raise ValueError(
                    f"Index is not interrupted: {index_id} ({index['status']})"
                )
            active = connection.execute(
                "SELECT 1 FROM documents WHERE active_index_id=?",
                (index_id,),
            ).fetchone()
            restored_status = (
                LifecycleStatus.ACTIVE.value
                if active is not None
                else LifecycleStatus.FAILED.value
            )
            connection.execute(
                """
                UPDATE document_indexes
                SET status=?, error_type=?, updated_at=?
                WHERE index_id=?
                """,
                (restored_status, "InterruptedRetryRequested", now, index_id),
            )
            connection.execute(
                """
                UPDATE index_operations
                SET status=?, error_type=?, updated_at=?, completed_at=?
                WHERE index_id=? AND status=?
                """,
                (
                    OperationStatus.FAILED.value,
                    "InterruptedRetryRequested",
                    now,
                    now,
                    index_id,
                    OperationStatus.RUNNING.value,
                ),
            )

    def active_index_ids(
        self,
        *,
        tenant_id: str | None = None,
        collection_id: str | None = None,
    ) -> tuple[str, ...]:
        clauses = ["active_index_id IS NOT NULL"]
        parameters: list[str] = []
        if tenant_id is not None:
            clauses.append("tenant_id=?")
            parameters.append(tenant_id)
        if collection_id is not None:
            clauses.append("collection_id=?")
            parameters.append(collection_id)
        query = (
            "SELECT active_index_id FROM documents WHERE "
            + " AND ".join(clauses)
            + " ORDER BY document_key"
        )
        with self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return tuple(row["active_index_id"] for row in rows)

    def index_ids_by_status(
        self,
        *statuses: LifecycleStatus,
        tenant_id: str | None = None,
        collection_id: str | None = None,
    ) -> tuple[str, ...]:
        if not statuses:
            return ()
        placeholders = ",".join("?" for _ in statuses)
        clauses = [f"i.status IN ({placeholders})"]
        parameters = [status.value for status in statuses]
        if tenant_id is not None:
            clauses.append("d.tenant_id=?")
            parameters.append(tenant_id)
        if collection_id is not None:
            clauses.append("d.collection_id=?")
            parameters.append(collection_id)
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT i.index_id
                FROM document_indexes i
                JOIN document_versions v
                  ON v.document_version_id=i.document_version_id
                JOIN documents d ON d.document_key=v.document_key
                WHERE {' AND '.join(clauses)}
                ORDER BY i.index_id
                """,
                parameters,
            ).fetchall()
        return tuple(row["index_id"] for row in rows)

    def all_index_ids(
        self,
        *,
        tenant_id: str | None = None,
        collection_id: str | None = None,
    ) -> tuple[str, ...]:
        clauses: list[str] = []
        parameters: list[str] = []
        if tenant_id is not None:
            clauses.append("d.tenant_id=?")
            parameters.append(tenant_id)
        if collection_id is not None:
            clauses.append("d.collection_id=?")
            parameters.append(collection_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT i.index_id FROM document_indexes i "
                "JOIN document_versions v "
                "ON v.document_version_id=i.document_version_id "
                "JOIN documents d ON d.document_key=v.document_key"
                + where
                + " ORDER BY i.index_id",
                parameters,
            ).fetchall()
        return tuple(row["index_id"] for row in rows)

    def get_document(self, document_key: str) -> dict | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM documents WHERE document_key=?",
                (document_key,),
            ).fetchone()
        return dict(row) if row else None

    def get_index(self, index_id: str) -> dict | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT i.*, v.document_key, v.source_sha256, v.source_path,
                       v.file_type, v.file_size_bytes, d.display_name,
                       d.tenant_id, d.collection_id
                FROM document_indexes i
                JOIN document_versions v
                  ON v.document_version_id=i.document_version_id
                JOIN documents d ON d.document_key=v.document_key
                WHERE i.index_id=?
                """,
                (index_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_documents(
        self,
        *,
        tenant_id: str | None = None,
        collection_id: str | None = None,
    ) -> tuple[dict, ...]:
        clauses: list[str] = []
        parameters: list[str] = []
        if tenant_id is not None:
            clauses.append("tenant_id=?")
            parameters.append(tenant_id)
        if collection_id is not None:
            clauses.append("collection_id=?")
            parameters.append(collection_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM documents"
                + where
                + " ORDER BY display_name, document_key",
                parameters,
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def list_indexes(
        self,
        *,
        document_key: str | None = None,
        tenant_id: str | None = None,
        collection_id: str | None = None,
    ) -> tuple[dict, ...]:
        clauses: list[str] = []
        parameters: list[str] = []
        if document_key is not None:
            clauses.append("v.document_key=?")
            parameters.append(document_key)
        if tenant_id is not None:
            clauses.append("d.tenant_id=?")
            parameters.append(tenant_id)
        if collection_id is not None:
            clauses.append("d.collection_id=?")
            parameters.append(collection_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        query = (
            "SELECT i.*, v.document_key, v.source_sha256, v.source_path, "
            "v.file_type, v.file_size_bytes, d.display_name, "
            "d.tenant_id, d.collection_id, d.active_index_id, "
            "(SELECT o.error_type FROM index_operations o "
            " WHERE o.index_id=i.index_id AND o.status=? "
            " ORDER BY o.updated_at DESC LIMIT 1) AS last_operation_error_type "
            "FROM document_indexes i "
            "JOIN document_versions v ON v.document_version_id=i.document_version_id "
            "JOIN documents d ON d.document_key=v.document_key"
            + where
            + " ORDER BY d.display_name, i.created_at, i.index_id"
        )
        with self._connection() as connection:
            rows = connection.execute(
                query,
                [OperationStatus.FAILED.value, *parameters],
            ).fetchall()
        return tuple(dict(row) for row in rows)
