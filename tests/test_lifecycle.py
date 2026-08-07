import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.documents import Document

from app.core.document_chunker import DocumentChunker
from app.core.document_loader import UniversalDocumentLoader
from app.core.embedding_client import UniversalEmbeddingClient
from app.core.vector_store import VectorStore
from app.lifecycle.models import (
    IndexManifest,
    LifecycleStatus,
    RebuildPlan,
    build_document_version_id,
    build_index_id,
)
from app.lifecycle.registry import DocumentRegistry
from app.lifecycle.service import DocumentLifecycleService


class FakeEmbeddingClient:
    provider = "fake"
    config = {"model": "fake-model", "dimensions": 4}

    @staticmethod
    def _vector(text):
        values = [0.0] * 4
        for index, character in enumerate(text.encode("utf-8")):
            values[index % 4] += float(character)
        return values

    def embed_text(self, text):
        return self._vector(text)

    def embed_texts_batch(self, texts, show_progress=False):
        return [self._vector(text) for text in texts]


class FailingEmbeddingClient(FakeEmbeddingClient):
    def embed_texts_batch(self, texts, show_progress=False):
        raise RuntimeError("embedding unavailable")


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="rag-lifecycle-"))
        self.source_path = self.directory / "guide.txt"
        self.source_path.write_text("第一版文档内容。" * 30, encoding="utf-8")
        self.registry = DocumentRegistry(str(self.directory / "registry.sqlite3"))
        self.vector_store = VectorStore(
            collection_name="lifecycle_documents",
            persist_directory=str(self.directory / "chroma"),
        )

    def tearDown(self):
        import shutil

        self.vector_store.close()
        self.vector_store = None
        shutil.rmtree(self.directory, ignore_errors=True)

    def _service(
        self,
        embedding_client=None,
        *,
        chunk_size=80,
        tenant_id="default",
    ):
        return DocumentLifecycleService(
            loader=UniversalDocumentLoader(),
            chunker=DocumentChunker(chunk_size=chunk_size, chunk_overlap=10),
            embedding_client=embedding_client or FakeEmbeddingClient(),
            vector_store=self.vector_store,
            registry=self.registry,
            upload_dir=str(self.directory / "uploads"),
            tenant_id=tenant_id,
        )

    def test_same_content_is_noop_and_content_update_switches_active_index(self):
        service = self._service()

        first = service.ingest(self.source_path)
        duplicate = service.ingest(self.source_path)

        self.assertEqual(first.status, "indexed")
        self.assertEqual(duplicate.status, "noop")
        self.assertEqual(duplicate.index_id, first.index_id)
        self.assertEqual(self.vector_store.count_by_index_id(first.index_id), first.chunk_count)

        self.source_path.write_text("第二版文档内容，已经发生变化。" * 30, encoding="utf-8")
        second = service.ingest(self.source_path)

        self.assertEqual(second.status, "indexed")
        self.assertNotEqual(second.index_id, first.index_id)
        self.assertEqual(second.previous_index_id, first.index_id)
        self.assertEqual(self.vector_store.count_by_index_id(first.index_id), 0)
        self.assertEqual(
            self.registry.get_document(first.document_key)["active_index_id"],
            second.index_id,
        )
        self.assertEqual(
            self.registry.get_index(first.index_id)["status"],
            LifecycleStatus.DELETED.value,
        )

    def test_failed_new_version_keeps_previous_active_index(self):
        service = self._service()
        first = service.ingest(self.source_path)
        self.source_path.write_text("无法完成向量化的新版本。" * 30, encoding="utf-8")

        with self.assertRaises(RuntimeError):
            self._service(FailingEmbeddingClient()).ingest(self.source_path)

        document = self.registry.get_document(first.document_key)
        self.assertEqual(document["active_index_id"], first.index_id)
        self.assertEqual(self.vector_store.count_by_index_id(first.index_id), first.chunk_count)

    def test_active_metadata_predicate_hides_superseded_managed_chunks(self):
        service = self._service()
        first = service.ingest(self.source_path)
        self.source_path.write_text("第三版文档内容。" * 30, encoding="utf-8")
        second = service.ingest(self.source_path)

        predicate = service.active_metadata_predicate()
        self.assertFalse(predicate({"index_id": first.index_id}))
        self.assertTrue(predicate({"index_id": second.index_id}))
        self.assertTrue(predicate({"document_id": "legacy-document"}))

    def test_rebuild_dry_run_does_not_change_registry_or_vectors(self):
        service = self._service()
        first = service.ingest(self.source_path)

        plan = service.rebuild_document(first.document_key, dry_run=True)

        self.assertIsInstance(plan, RebuildPlan)
        self.assertEqual(plan.current_index_id, first.index_id)
        self.assertEqual(plan.planned_index_id, first.index_id)
        self.assertEqual(self.vector_store.count_by_index_id(first.index_id), first.chunk_count)
        self.assertEqual(
            self.registry.get_index(first.index_id)["status"],
            LifecycleStatus.ACTIVE.value,
        )

    def test_rebuild_failure_restores_active_index(self):
        service = self._service()
        first = service.ingest(self.source_path)

        with self.assertRaises(RuntimeError):
            self._service(FailingEmbeddingClient()).rebuild_document(first.document_key)

        self.assertEqual(
            self.registry.get_document(first.document_key)["active_index_id"],
            first.index_id,
        )
        self.assertEqual(
            self.registry.get_index(first.index_id)["status"],
            LifecycleStatus.ACTIVE.value,
        )
        self.assertEqual(self.vector_store.count_by_index_id(first.index_id), first.chunk_count)

    def test_interrupted_active_rebuild_can_be_explicitly_retried(self):
        service = self._service()
        first = service.ingest(self.source_path)
        manifest = service._manifest()
        claim = self.registry.claim_index(
            document_key=first.document_key,
            document_version_id=first.document_version_id,
            index_id=first.index_id,
            tenant_id=service.tenant_id,
            collection_id=service.collection_id,
            display_name=self.source_path.name,
            source_sha256=first.source_sha256,
            source_path=self.registry.get_index(first.index_id)["source_path"],
            file_type=".txt",
            file_size_bytes=self.source_path.stat().st_size,
            manifest=manifest,
            operation_type="rebuild",
            force=True,
        )
        self.assertEqual(claim.action, "build")
        self.assertEqual(
            self.registry.get_index(first.index_id)["status"],
            LifecycleStatus.INDEXING.value,
        )

        rebuilt = service.rebuild_document(first.document_key, retry=True)

        self.assertEqual(rebuilt.status, "indexed")
        self.assertEqual(
            self.registry.get_index(first.index_id)["status"],
            LifecycleStatus.ACTIVE.value,
        )

    def test_audit_and_cleanup_handle_orphan_indexes(self):
        service = self._service()
        first = service.ingest(self.source_path)
        orphan = Document(
            page_content="orphan chunk",
            metadata={"index_id": "orphan-index", "chunk_id": "orphan-chunk"},
        )
        self.vector_store.add_documents([orphan], [[1.0, 0.0, 0.0, 0.0]])

        report = service.audit()
        self.assertEqual(report.orphan_index_ids, ("orphan-index",))
        dry_run = service.cleanup(include_orphans=True, dry_run=True)
        self.assertEqual(dry_run.orphan_index_ids, ("orphan-index",))
        self.assertEqual(self.vector_store.count_by_index_id("orphan-index"), 1)

        cleaned = service.cleanup(include_orphans=True)

        self.assertEqual(cleaned.orphan_index_ids, ())
        self.assertEqual(self.vector_store.count_by_index_id("orphan-index"), 0)
        self.assertEqual(self.vector_store.count_by_index_id(first.index_id), first.chunk_count)

    def test_cleanup_recovers_when_vectors_were_deleted_before_status_update(self):
        service = self._service()
        first = service.ingest(self.source_path)
        self.source_path.write_text("replacement content " * 30, encoding="utf-8")
        delete_vectors = self.vector_store.delete_by_index_id

        with patch.object(
            self.vector_store,
            "delete_by_index_id",
            side_effect=RuntimeError("interrupted cleanup"),
        ):
            second = service.ingest(self.source_path)

        self.assertTrue(second.cleanup_pending)
        self.assertEqual(
            self.registry.get_index(first.index_id)["status"],
            LifecycleStatus.DELETING.value,
        )
        delete_vectors(first.index_id)
        report = service.audit()
        self.assertIn(first.index_id, report.stale_index_ids)

        cleaned = service.cleanup()

        self.assertNotIn(first.index_id, cleaned.stale_index_ids)
        self.assertEqual(
            self.registry.get_index(first.index_id)["status"],
            LifecycleStatus.DELETED.value,
        )

    def test_audit_detects_partial_and_missing_active_index_and_upload_repairs_it(self):
        service = self._service()
        first = service.ingest(self.source_path)
        chunk_ids = self.vector_store.list_ids_by_index_id(first.index_id)
        self.vector_store.delete_by_ids(chunk_ids[:1])

        partial = service.audit()
        self.assertEqual(partial.mismatched_active_index_ids, (first.index_id,))
        self.assertFalse(partial.healthy)

        self.vector_store.delete_by_index_id(first.index_id)
        missing = service.audit()
        self.assertEqual(missing.missing_active_index_ids, (first.index_id,))

        repaired = service.ingest(self.source_path)

        self.assertEqual(repaired.status, "indexed")
        self.assertEqual(repaired.index_id, first.index_id)
        self.assertTrue(service.audit().healthy)

    def test_rebuild_reconciles_unexpected_chunk_ids(self):
        service = self._service()
        first = service.ingest(self.source_path)
        unexpected_id = "unexpected-managed-chunk"
        self.vector_store.add_documents(
            [
                Document(
                    page_content="unexpected",
                    metadata={
                        "index_id": first.index_id,
                        "chunk_id": unexpected_id,
                    },
                )
            ],
            [[1.0, 0.0, 0.0, 0.0]],
        )

        rebuilt = service.rebuild_document(first.document_key)

        self.assertEqual(rebuilt.index_id, first.index_id)
        self.assertNotIn(
            unexpected_id,
            self.vector_store.list_ids_by_index_id(first.index_id),
        )
        self.assertTrue(service.audit().healthy)

    def test_rebuild_plan_uses_current_configuration(self):
        first = self._service().ingest(self.source_path)

        plan = self._service(chunk_size=70).plan_rebuild_document(
            first.document_key
        )

        self.assertTrue(plan.configuration_changed)
        self.assertEqual(plan.reason, "configuration_changed")
        self.assertNotEqual(plan.current_index_id, plan.planned_index_id)
        self.assertNotEqual(
            plan.current_index_fingerprint,
            plan.planned_index_fingerprint,
        )

    def test_manifest_only_plan_reuses_verified_dimension_for_same_model(self):
        first = self._service().ingest(self.source_path)
        descriptor = SimpleNamespace(
            provider="fake",
            config={"model": "fake-model", "dimensions": 999},
            manifest_only=True,
        )

        plan = self._service(descriptor).plan_rebuild_document(first.document_key)

        self.assertFalse(plan.configuration_changed)
        self.assertEqual(plan.planned_index_id, first.index_id)

    def test_rebuild_rejects_corrupted_persisted_source(self):
        service = self._service()
        first = service.ingest(self.source_path)
        index = self.registry.get_index(first.index_id)
        persisted = Path(service.upload_dir) / str(index["source_path"])
        persisted.write_text("corrupted source", encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "integrity check failed"):
            service.plan_rebuild_document(first.document_key)

    def test_audit_does_not_treat_another_tenant_as_orphan(self):
        tenant_a = self._service(tenant_id="tenant-a")
        tenant_b = self._service(tenant_id="tenant-b")
        first = tenant_a.ingest(self.source_path)
        second = tenant_b.ingest(self.source_path)

        report = tenant_a.cleanup(include_orphans=True)

        self.assertEqual(report.active_index_ids, (first.index_id,))
        self.assertEqual(report.orphan_index_ids, ())
        self.assertEqual(
            self.vector_store.count_by_index_id(second.index_id),
            second.chunk_count,
        )
        with self.assertRaisesRegex(KeyError, "current scope"):
            tenant_a.plan_rebuild_document(second.document_key)

    def test_retry_recovers_interrupted_non_active_version(self):
        service = self._service()
        first = service.ingest(self.source_path)
        self.source_path.write_text("interrupted new version " * 30, encoding="utf-8")
        persisted = service.persist_source_file(self.source_path, service.upload_dir)
        source_sha256 = service._sha256_file(persisted)
        document_version_id = build_document_version_id(
            first.document_key,
            source_sha256,
        )
        manifest = service._manifest()
        index_id = build_index_id(document_version_id, manifest.fingerprint)
        claim = self.registry.claim_index(
            document_key=first.document_key,
            document_version_id=document_version_id,
            index_id=index_id,
            tenant_id=service.tenant_id,
            collection_id=service.collection_id,
            display_name=self.source_path.name,
            source_sha256=source_sha256,
            source_path=persisted.name,
            file_type=".txt",
            file_size_bytes=persisted.stat().st_size,
            manifest=manifest,
        )
        self.assertEqual(claim.action, "build")
        self.assertEqual(
            self.registry.get_document(first.document_key)["active_index_id"],
            first.index_id,
        )

        retried = service.rebuild_document(first.document_key, retry=True)

        self.assertEqual(retried.index_id, index_id)
        self.assertEqual(
            self.registry.get_document(first.document_key)["active_index_id"],
            index_id,
        )
        self.assertEqual(
            self.registry.get_index(first.index_id)["status"],
            LifecycleStatus.DELETED.value,
        )

    def test_retry_rejects_changed_configuration_without_releasing_claim(self):
        service = self._service()
        first = service.ingest(self.source_path)
        index = self.registry.get_index(first.index_id)
        claim = self.registry.claim_index(
            document_key=first.document_key,
            document_version_id=first.document_version_id,
            index_id=first.index_id,
            tenant_id=service.tenant_id,
            collection_id=service.collection_id,
            display_name=self.source_path.name,
            source_sha256=first.source_sha256,
            source_path=index["source_path"],
            file_type=".txt",
            file_size_bytes=self.source_path.stat().st_size,
            manifest=service._manifest(),
            operation_type="rebuild",
            force=True,
        )
        self.assertEqual(claim.action, "build")

        with self.assertRaisesRegex(ValueError, "changed configuration"):
            self._service(chunk_size=70).rebuild_document(
                first.document_key,
                retry=True,
            )

        self.assertEqual(
            self.registry.get_index(first.index_id)["status"],
            LifecycleStatus.INDEXING.value,
        )


class RegistryTests(unittest.TestCase):
    def test_claim_retry_activation_and_noop(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = DocumentRegistry(str(Path(directory) / "registry.sqlite3"))
            manifest = IndexManifest(
                schema_version=1,
                parser="test-parser",
                chunker="test-chunker",
                chunk_size=100,
                chunk_overlap=10,
                embedding_provider="fake",
                embedding_model="fake-model",
                embedding_dimension=4,
            )
            fields = dict(
                document_key="document",
                document_version_id="version",
                index_id="index",
                tenant_id="default",
                collection_id="collection",
                display_name="guide.txt",
                source_sha256="a" * 64,
                source_path="source.txt",
                file_type=".txt",
                file_size_bytes=10,
                manifest=manifest,
            )

            first = registry.claim_index(**fields)
            self.assertEqual(first.action, "build")
            in_progress = registry.claim_index(**fields)
            self.assertEqual(in_progress.action, "in_progress")

            registry.fail_index("index", first.operation_id, "RuntimeError")
            retry = registry.claim_index(**fields)
            self.assertEqual(retry.action, "build")
            registry.activate_index(
                document_key="document",
                index_id="index",
                operation_id=retry.operation_id,
                chunk_count=2,
            )
            noop = registry.claim_index(**fields)
            self.assertEqual(noop.action, "noop")

    def test_activation_rejects_index_owned_by_another_document(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = DocumentRegistry(str(Path(directory) / "registry.sqlite3"))
            manifest = IndexManifest(
                schema_version=1,
                parser="test-parser",
                chunker="test-chunker",
                chunk_size=100,
                chunk_overlap=10,
                embedding_provider="fake",
                embedding_model="fake-model",
                embedding_dimension=4,
            )
            common = {
                "tenant_id": "default",
                "collection_id": "collection",
                "display_name": "guide.txt",
                "source_sha256": "a" * 64,
                "source_path": "source.txt",
                "file_type": ".txt",
                "file_size_bytes": 10,
                "manifest": manifest,
            }
            first = registry.claim_index(
                document_key="document-1",
                document_version_id="version-1",
                index_id="index-1",
                **common,
            )
            second = registry.claim_index(
                document_key="document-2",
                document_version_id="version-2",
                index_id="index-2",
                **{**common, "source_sha256": "b" * 64},
            )

            with self.assertRaisesRegex(ValueError, "does not belong"):
                registry.activate_index(
                    document_key="document-1",
                    index_id="index-2",
                    operation_id=second.operation_id,
                    chunk_count=1,
                )

            self.assertEqual(
                registry.get_index("index-1")["status"],
                LifecycleStatus.INDEXING.value,
            )
            self.assertEqual(first.action, "build")


if __name__ == "__main__":
    unittest.main()
