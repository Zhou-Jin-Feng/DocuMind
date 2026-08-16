"""同步且可恢复的文档摄取、索引切换、审计与清理流程。"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Callable

from langchain_core.documents import Document

from app.core.document_chunker import DocumentChunker
from app.core.document_loader import UniversalDocumentLoader
from app.lifecycle.models import (
    DocumentDeletionResult,
    IndexAuditReport,
    IndexManifest,
    IngestionResult,
    LifecycleStatus,
    RebuildPlan,
    build_document_key,
    build_document_version_id,
    build_index_id,
)
from app.lifecycle.registry import DocumentRegistry
from app.observability.tracing import trace_span
from app.utils.logger import get_logger


logger = get_logger(__name__)


class IndexOperationInProgress(RuntimeError):
    """同一索引已被另一个请求认领时抛出。"""


class DocumentLifecycleService:
    """
    编排源文件、SQLite 注册表和 Milvus 之间的文档生命周期。

    新索引只有在向量数量核对通过后才会原子激活；构建期间旧索引继续服务，
    因此检索不会看到半成品版本。激活后的旧向量清理允许失败并稍后恢复。
    """

    def __init__(
        self,
        *,
        loader: UniversalDocumentLoader,
        chunker: DocumentChunker,
        embedding_client,
        vector_store,
        registry: DocumentRegistry,
        upload_dir: str,
        tenant_id: str = "default",
        collection_id: str = "rag_documents",
    ):
        self.loader = loader
        self.chunker = chunker
        self.embedding_client = embedding_client
        self.vector_store = vector_store
        self.registry = registry
        self.upload_dir = str(upload_dir)
        self.tenant_id = tenant_id
        self.collection_id = collection_id

    @staticmethod
    def _sha256_file(file_path: Path) -> str:
        digest = hashlib.sha256()
        with file_path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @classmethod
    def persist_source_file(cls, file_path: Path, upload_dir: str) -> Path:
        """
        以内容哈希命名并原子保存源文件。

        临时文件与目标位于同一目录，``os.replace`` 不会暴露半写入文件；相同
        内容重复上传直接复用已有文件。
        """
        target_dir = Path(upload_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        source_hash = cls._sha256_file(file_path)
        destination = target_dir / f"{source_hash}{file_path.suffix.lower()}"

        if destination.is_file():
            if (
                destination.stat().st_size == file_path.stat().st_size
                and cls._sha256_file(destination) == source_hash
            ):
                return destination

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix=f".{source_hash}.",
                suffix=".tmp",
                dir=target_dir,
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                with file_path.open("rb") as source:
                    shutil.copyfileobj(source, temporary)
            os.replace(temporary_path, destination)
            return destination
        except Exception:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise

    def _manifest(self) -> IndexManifest:
        """固定所有会改变索引结果的解析、分块和 Embedding 配置。"""
        config = getattr(self.embedding_client, "config", {}) or {}
        model = str(
            config.get("model")
            or getattr(self.embedding_client, "model_name", "unknown")
        )
        dimension = int(
            config.get("dimensions")
            or config.get("dimension")
            or getattr(self.embedding_client, "embedding_dimension", 0)
            or 0
        )
        if dimension <= 0:
            raise ValueError(
                "Embedding dimension must be available before indexing; "
                "configure the provider or expose embedding_client.config['dimensions']"
            )
        return IndexManifest(
            schema_version=1,
            parser="UniversalDocumentLoader:v1",
            chunker="RecursiveCharacterTextSplitter:v1",
            chunk_size=self.chunker.chunk_size,
            chunk_overlap=self.chunker.chunk_overlap,
            embedding_provider=str(getattr(self.embedding_client, "provider", "unknown")),
            embedding_model=model,
            embedding_dimension=dimension,
        )

    def _decorate_source_metadata(
        self,
        documents: list[Document],
        *,
        display_name: str,
        document_key: str,
        document_version_id: str,
        index_id: str,
        index_fingerprint: str,
    ) -> None:
        """把三层身份和作用域写入页面及 Chunk，供过滤、审计和引用使用。"""
        for document in documents:
            document.metadata.update(
                {
                    "document_id": document_key,
                    "document_key": document_key,
                    "document_version_id": document_version_id,
                    "index_id": index_id,
                    "index_fingerprint": index_fingerprint,
                    "tenant_id": self.tenant_id,
                    "collection_id": self.collection_id,
                    "source": display_name,
                    "source_file": display_name,
                }
            )

    def active_metadata_predicate(self) -> Callable[[dict], bool]:
        """
        返回仅允许活动索引的谓词；没有生命周期元数据的旧向量暂时放行。

        该兼容行为只服务历史数据迁移，完成全量重建后可收紧为强制 index_id。
        """
        active_ids = set(
            self.registry.active_index_ids(
                tenant_id=self.tenant_id,
                collection_id=self.collection_id,
            )
        )

        def is_active(metadata: dict) -> bool:
            index_id = metadata.get("index_id")
            if not index_id:
                # Legacy v1.4 vectors have no lifecycle metadata yet.
                return True
            return str(index_id) in active_ids

        return is_active

    def ingest(
        self,
        source_path: str | Path,
        *,
        display_name: str | None = None,
        operation_type: str = "ingest",
        force: bool = False,
    ) -> IngestionResult:
        """
        摄取文档并以“先构建、后切换”的顺序发布新索引。

        流程为：持久化源文件、计算稳定身份、认领操作、加载与分块、向量化、
        Upsert、核对数量、激活新索引、尽力清理旧索引。任一步失败都会记录
        失败状态并继续抛出异常，不把部分结果报告为成功。
        """
        source = Path(source_path)
        if not source.is_file():
            raise FileNotFoundError(f"Source file does not exist: {source}")
        display_name = display_name or source.name
        persisted = self.persist_source_file(source, self.upload_dir)
        source_sha256 = self._sha256_file(persisted)
        document_key = build_document_key(
            display_name,
            tenant_id=self.tenant_id,
            collection_id=self.collection_id,
        )
        document_version_id = build_document_version_id(
            document_key,
            source_sha256,
        )
        manifest = self._manifest()
        index_id = build_index_id(document_version_id, manifest.fingerprint)
        claim_parameters = {
            "document_key": document_key,
            "document_version_id": document_version_id,
            "index_id": index_id,
            "tenant_id": self.tenant_id,
            "collection_id": self.collection_id,
            "display_name": display_name,
            "source_sha256": source_sha256,
            "source_path": persisted.name,
            "file_type": source.suffix.lower(),
            "file_size_bytes": persisted.stat().st_size,
            "manifest": manifest,
            "operation_type": operation_type,
        }
        claim = self.registry.claim_index(**claim_parameters, force=force)

        if claim.action == "noop":
            # 注册表相同不代表向量一定完整；计数不一致时自动进入修复构建。
            index = self.registry.get_index(index_id) or {}
            expected_count = int(index.get("chunk_count", 0))
            actual_count = self.vector_store.count_by_index_id(index_id)
            if expected_count > 0 and actual_count == expected_count:
                return IngestionResult(
                    status="noop",
                    operation_id=claim.operation_id,
                    document_key=document_key,
                    document_version_id=document_version_id,
                    index_id=index_id,
                    source_sha256=source_sha256,
                    chunk_count=expected_count,
                    collection_count=self.vector_store.count(),
                    previous_index_id=claim.previous_index_id,
                )
            logger.warning(
                "Active index is inconsistent; rebuilding instead of returning no-op",
                event="active_index_repair_started",
                operation="rag.document.ingest",
                status="started",
                index_id=index_id,
                expected_chunk_count=expected_count,
                actual_chunk_count=actual_count,
            )
            claim = self.registry.claim_index(**claim_parameters, force=True)
        if claim.action == "in_progress":
            raise IndexOperationInProgress(
                f"Index operation already running: {claim.operation_id}"
            )

        chunks: list[Document] = []
        active_operation = "document.load"
        try:
            with trace_span(
                "document.load",
                attributes={"file.extension": source.suffix.lower()},
            ):
                documents = self.loader.load_document(str(persisted))
            logger.info(
                "文档加载完成",
                event="document_loaded",
                operation=active_operation,
                status="success",
                document_count=len(documents),
                file_extension=source.suffix.lower(),
            )
            if not documents:
                raise ValueError("Document has no readable content")

            self._decorate_source_metadata(
                documents,
                display_name=display_name,
                document_key=document_key,
                document_version_id=document_version_id,
                index_id=index_id,
                index_fingerprint=manifest.fingerprint,
            )
            active_operation = "document.chunk"
            with trace_span("document.chunk", attributes={"document.count": len(documents)}):
                chunks = self.chunker.chunk_documents_recursive(documents)
            self._decorate_source_metadata(
                chunks,
                display_name=display_name,
                document_key=document_key,
                document_version_id=document_version_id,
                index_id=index_id,
                index_fingerprint=manifest.fingerprint,
            )
            logger.info(
                "文档分块完成",
                event="document_chunked",
                operation=active_operation,
                status="success",
                chunk_count=len(chunks),
            )
            if not chunks:
                raise ValueError("Document produced no non-empty chunks")

            texts = [chunk.page_content for chunk in chunks]
            active_operation = "embedding.batch"
            with trace_span(
                "embedding.batch",
                attributes={"provider": manifest.embedding_provider, "chunk.count": len(chunks)},
            ):
                embeddings = self.embedding_client.embed_texts_batch(
                    texts,
                    show_progress=False,
                )
            if len(embeddings) != len(chunks):
                raise ValueError("Embedding count does not match chunk count")
            actual_dimension = len(embeddings[0]) if embeddings else 0
            if actual_dimension != manifest.embedding_dimension:
                raise ValueError(
                    "Embedding dimension does not match the index manifest: "
                    f"{actual_dimension} != {manifest.embedding_dimension}"
                )
            if any(len(embedding) != actual_dimension for embedding in embeddings):
                raise ValueError("Embedding dimensions are inconsistent")
            self.registry.update_progress(
                claim.operation_id,
                chunks_total=len(chunks),
                chunks_indexed=0,
            )
            logger.info(
                "文档向量化完成",
                event="document_embedding_completed",
                operation=active_operation,
                status="success",
                provider=manifest.embedding_provider,
                chunk_count=len(chunks),
                embedding_dimension=actual_dimension,
            )

            active_operation = "vector.upsert"
            with trace_span("vector.upsert", attributes={"chunk.count": len(chunks)}):
                ensure_embedding_space = getattr(
                    self.vector_store,
                    "ensure_embedding_space",
                    None,
                )
                if callable(ensure_embedding_space):
                    ensure_embedding_space(
                        manifest.embedding_provider,
                        manifest.embedding_model,
                        actual_dimension,
                    )
                stored_ids = self.vector_store.add_documents(chunks, embeddings)
                list_index_ids = getattr(
                    self.vector_store,
                    "list_ids_by_index_id",
                    None,
                )
                if callable(list_index_ids):
                    # 强制重建的 Chunk 边界可能减少，清掉同一 index_id 下的残留主键。
                    unexpected_ids = sorted(
                        set(list_index_ids(index_id)) - set(stored_ids)
                    )
                    self.vector_store.delete_by_ids(unexpected_ids)
            logger.info(
                "向量幂等写入完成",
                event="vector_upsert_completed",
                operation=active_operation,
                status="success",
                chunk_count=len(chunks),
                index_id=index_id,
            )
            self.registry.update_progress(
                claim.operation_id,
                chunks_total=len(chunks),
                chunks_indexed=len(chunks),
            )
            indexed_count = self.vector_store.count_by_index_id(index_id)
            if indexed_count != len(chunks):
                raise RuntimeError(
                    f"Indexed chunk count mismatch: {indexed_count} != {len(chunks)}"
                )

            # 数量核对通过后才切换活动指针，避免检索命中半成品索引。
            previous_index_id = self.registry.activate_index(
                document_key=document_key,
                index_id=index_id,
                operation_id=claim.operation_id,
                chunk_count=len(chunks),
            )
            cleanup_pending = False
            if previous_index_id and previous_index_id != index_id:
                # 新索引已可用，旧索引清理失败只需暴露待清理状态，不回滚发布。
                try:
                    self.registry.mark_index_deleting(previous_index_id)
                    self.vector_store.delete_by_index_id(previous_index_id)
                    self.registry.mark_index_deleted(previous_index_id)
                except Exception:
                    cleanup_pending = True
                    logger.exception(
                        "旧索引清理失败",
                        event="index_cleanup_failed",
                        operation="index.cleanup",
                        status="error",
                        index_id=previous_index_id,
                    )

            collection_count = self.vector_store.count()
            logger.info(
                "文档索引完成",
                event="document_indexing_completed",
                operation="rag.document.ingest",
                status="success",
                chunk_count=len(chunks),
                collection_count=collection_count,
                index_id=index_id,
                cleanup_pending=cleanup_pending,
            )
            return IngestionResult(
                status="indexed",
                operation_id=claim.operation_id,
                document_key=document_key,
                document_version_id=document_version_id,
                index_id=index_id,
                source_sha256=source_sha256,
                chunk_count=len(chunks),
                collection_count=collection_count,
                previous_index_id=previous_index_id,
                cleanup_pending=cleanup_pending,
            )
        except Exception as exc:
            # 注册表保留失败类型和操作进度，供详情页展示及显式重试。
            self.registry.fail_index(index_id, claim.operation_id, type(exc).__name__)
            logger.exception(
                "文档索引失败",
                event="document_indexing_completed",
                operation="rag.document.ingest",
                status="error",
                error_type=type(exc).__name__,
                failed_operation=active_operation,
                index_id=index_id,
                chunk_count=len(chunks),
            )
            raise

    def audit(self) -> IndexAuditReport:
        """对比 SQLite 预期状态和 Milvus 实际库存，分类缺失、残留与孤儿索引。"""
        tenant_scope = {
            "tenant_id": self.tenant_id,
            "collection_id": self.collection_id,
        }
        managed_ids = set(
            self.registry.all_index_ids(collection_id=self.collection_id)
        )
        active_ids = set(
            self.registry.active_index_ids(**tenant_scope)
        )
        stale_registry_ids = set(
            self.registry.index_ids_by_status(
                LifecycleStatus.SUPERSEDED,
                LifecycleStatus.FAILED,
                LifecycleStatus.DELETING,
                **tenant_scope,
            )
        )
        deleted_ids = set(
            self.registry.index_ids_by_status(
                LifecycleStatus.DELETED,
                **tenant_scope,
            )
        )
        index_counts, legacy_count = self.vector_store.index_inventory()
        vector_ids = set(index_counts)
        orphan_ids = vector_ids - managed_ids
        stale_ids = stale_registry_ids | (deleted_ids & vector_ids)
        missing_active_ids: set[str] = set()
        mismatched_active_ids: set[str] = set()
        for index_id in active_ids:
            index = self.registry.get_index(index_id)
            actual_count = index_counts.get(index_id, 0)
            if index is None or actual_count == 0:
                missing_active_ids.add(index_id)
                continue
            expected_count = int(index["chunk_count"])
            if actual_count != expected_count:
                mismatched_active_ids.add(index_id)
        return IndexAuditReport(
            active_index_ids=tuple(sorted(active_ids)),
            stale_index_ids=tuple(sorted(stale_ids)),
            orphan_index_ids=tuple(sorted(orphan_ids)),
            missing_active_index_ids=tuple(sorted(missing_active_ids)),
            legacy_chunk_count=legacy_count,
            mismatched_active_index_ids=tuple(sorted(mismatched_active_ids)),
        )

    def _registered_source_path(self, relative_path: str) -> Path:
        """解析注册路径，并拒绝通过 ``..`` 或绝对路径逃逸上传目录。"""
        source_root = Path(self.upload_dir).resolve()
        source = (source_root / relative_path).resolve()
        if source != source_root and source_root not in source.parents:
            raise ValueError("Registered source path escapes the upload directory")
        return source

    def _source_path_for_index(self, index: dict) -> Path:
        return self._registered_source_path(str(index["source_path"]))

    def _scoped_document(self, document_key: str) -> dict:
        document = self.registry.get_document(document_key)
        if document is None:
            raise KeyError(f"Unknown document: {document_key}")
        if (
            document["tenant_id"] != self.tenant_id
            or document["collection_id"] != self.collection_id
        ):
            raise KeyError(f"Unknown document in the current scope: {document_key}")
        return document

    def _plan_index(
        self,
        document: dict,
        index: dict,
        *,
        reason: str,
    ) -> RebuildPlan:
        """校验源文件和身份链后生成无副作用的重建计划。"""
        document_key = str(document["document_key"])
        if (
            index["document_key"] != document_key
            or index["tenant_id"] != self.tenant_id
            or index["collection_id"] != self.collection_id
        ):
            raise ValueError(
                f"Index {index['index_id']} does not belong to the current document scope"
            )
        active_index_id = document.get("active_index_id")
        source = self._source_path_for_index(index)
        if not source.is_file():
            raise FileNotFoundError(
                f"Persisted source file is missing for {document_key}: {source}"
            )
        registered_sha256 = str(index["source_sha256"])
        actual_sha256 = self._sha256_file(source)
        if actual_sha256 != registered_sha256:
            raise RuntimeError(
                f"Persisted source integrity check failed for {document_key}: "
                f"expected {registered_sha256}, got {actual_sha256}"
            )
        current_manifest = IndexManifest.from_json(str(index["manifest_json"]))
        planned_manifest = self._manifest()
        if (
            getattr(self.embedding_client, "manifest_only", False)
            and planned_manifest.embedding_provider
            == current_manifest.embedding_provider
            and planned_manifest.embedding_model == current_manifest.embedding_model
        ):
            planned_manifest = replace(
                planned_manifest,
                embedding_dimension=current_manifest.embedding_dimension,
            )
        planned_version_id = build_document_version_id(
            document_key,
            registered_sha256,
        )
        if planned_version_id != str(index["document_version_id"]):
            raise RuntimeError(
                f"Registered document version is inconsistent: "
                f"{index['document_version_id']} != {planned_version_id}"
            )
        planned_index_id = build_index_id(
            planned_version_id,
            planned_manifest.fingerprint,
        )
        configuration_changed = (
            current_manifest.fingerprint != planned_manifest.fingerprint
        )
        active_index = (
            self.registry.get_index(str(active_index_id))
            if active_index_id
            else None
        )
        return RebuildPlan(
            status="planned",
            document_key=document_key,
            display_name=str(index["display_name"]),
            source_path=str(source),
            current_index_id=str(active_index_id) if active_index_id else None,
            planned_index_id=planned_index_id,
            source_sha256=registered_sha256,
            reason="configuration_changed" if configuration_changed else reason,
            current_index_fingerprint=(
                str(active_index["index_fingerprint"])
                if active_index is not None
                else None
            ),
            planned_index_fingerprint=planned_manifest.fingerprint,
            configuration_changed=configuration_changed,
            target_index_id=str(index["index_id"]),
            target_index_fingerprint=current_manifest.fingerprint,
        )

    def plan_rebuild_document(self, document_key: str) -> RebuildPlan:
        """基于当前活动索引规划一次完整重建。"""
        document = self._scoped_document(document_key)
        active_index_id = document.get("active_index_id")
        if not active_index_id:
            raise ValueError(f"Document has no active index: {document_key}")
        index = self.registry.get_index(str(active_index_id))
        if index is None:
            raise ValueError(f"Active index is missing from registry: {active_index_id}")
        return self._plan_index(
            document,
            index,
            reason="force_rebuild_current_manifest",
        )

    def plan_retry_document(self, document_key: str) -> RebuildPlan:
        """仅在目标唯一时规划中断索引的原配置重试。"""
        document = self._scoped_document(document_key)
        interrupted = [
            index
            for index in self.registry.list_indexes(document_key=document_key)
            if index["status"] == LifecycleStatus.INDEXING.value
        ]
        if not interrupted:
            raise ValueError(f"Document has no interrupted index: {document_key}")
        if len(interrupted) > 1:
            raise ValueError(
                f"Document has multiple interrupted indexes; retry target is ambiguous: "
                f"{document_key}"
            )
        return self._plan_index(
            document,
            interrupted[0],
            reason="retry_interrupted_index",
        )

    def rebuild_document(
        self,
        document_key: str,
        *,
        dry_run: bool = False,
        retry: bool = False,
    ) -> IngestionResult | RebuildPlan:
        """
        执行重建或中断重试；``dry_run`` 只返回计划，不认领操作或写向量。

        Retry 必须保持原索引身份，配置已改变时要求走普通重建，避免把新配置
        写入旧 ``index_id``。
        """
        plan = (
            self.plan_retry_document(document_key)
            if retry
            else self.plan_rebuild_document(document_key)
        )
        if dry_run:
            return plan
        source = Path(plan.source_path)
        if retry:
            if plan.target_index_id != plan.planned_index_id:
                raise ValueError(
                    "Cannot retry an interrupted index with changed configuration; "
                    "rebuild without --retry or restore the previous configuration"
                )
            self.registry.reset_index_for_retry(str(plan.target_index_id))
        return self.ingest(
            source,
            display_name=plan.display_name,
            operation_type="rebuild",
            force=True,
        )

    def delete_document(self, document_key: str) -> DocumentDeletionResult:
        """
        先从活动集合隐藏文档，再删除向量，最后移除注册记录和无引用源文件。

        源文件清理失败不会撤销已完成的数据删除，而是通过 ``cleanup_pending``
        暴露给调用方。
        """
        self._scoped_document(document_key)
        index_ids = self.registry.claim_document_deletion(
            document_key,
            tenant_id=self.tenant_id,
            collection_id=self.collection_id,
        )
        deleted_chunk_count = 0
        with trace_span("rag.document.delete"):
            for index_id in index_ids:
                deleted_chunk_count += self.vector_store.count_by_index_id(index_id)
                self.vector_store.delete_by_index_id(index_id)

            unreferenced_paths = self.registry.finalize_document_deletion(
                document_key,
                tenant_id=self.tenant_id,
                collection_id=self.collection_id,
            )

        cleanup_pending = False
        for relative_path in unreferenced_paths:
            try:
                self._registered_source_path(relative_path).unlink(missing_ok=True)
            except OSError:
                cleanup_pending = True
                logger.warning(
                    "文档源文件清理失败",
                    event="document_source_cleanup_failed",
                    operation="rag.document.delete",
                    status="warning",
                    error_type="OSError",
                )

        return DocumentDeletionResult(
            status="deleted",
            document_key=document_key,
            deleted_index_count=len(index_ids),
            deleted_chunk_count=deleted_chunk_count,
            collection_count=self.vector_store.count(),
            cleanup_pending=cleanup_pending,
        )

    def cleanup(
        self,
        *,
        include_orphans: bool = False,
        dry_run: bool = False,
    ) -> IndexAuditReport:
        """
        清理可确认的旧索引；孤儿向量必须显式启用 ``include_orphans``。

        默认保守策略避免误删来自其他注册表或人工导入的未知向量。
        """
        report = self.audit()
        if dry_run:
            return report
        targets = set(report.stale_index_ids)
        if include_orphans:
            targets.update(report.orphan_index_ids)
        for index_id in sorted(targets):
            index = self.registry.get_index(index_id)
            belongs_to_scope = bool(
                index
                and index["tenant_id"] == self.tenant_id
                and index["collection_id"] == self.collection_id
            )
            if belongs_to_scope:
                self.registry.mark_index_deleting(index_id)
                self.vector_store.delete_by_index_id(index_id)
                self.registry.mark_index_deleted(index_id)
            elif index is None:
                self.vector_store.delete_by_index_id(index_id)
        return self.audit()

    def close(self) -> None:
        """释放生命周期服务持有的向量存储资源。"""
        close = getattr(self.vector_store, "close", None)
        if callable(close):
            close()
