import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from app.lifecycle.cli import _build_service, main
from app.lifecycle.models import IndexAuditReport, RebuildPlan


class FakeRegistry:
    @staticmethod
    def list_documents(**kwargs):
        return (
            {
                "document_key": "document-1",
                "display_name": "guide.txt",
                "active_index_id": "index-1",
            },
        )

    @staticmethod
    def list_indexes(**kwargs):
        return ({"index_id": "index-1", "status": "active"},)


class FakeService:
    tenant_id = "default"
    collection_id = "rag_documents"
    registry = FakeRegistry()
    vector_store = type("FakeStore", (), {"count": staticmethod(lambda: 3)})()

    @staticmethod
    def audit():
        return IndexAuditReport(("index-1",), (), (), ())

    @staticmethod
    def cleanup(**kwargs):
        return IndexAuditReport(("index-1",), (), (), ())

    @staticmethod
    def rebuild_document(document_key, *, dry_run=False, retry=False):
        return RebuildPlan(
            status="planned",
            document_key=document_key,
            display_name="guide.txt",
            source_path="data/uploads/hash.txt",
            current_index_id="index-1",
            planned_index_id="index-1",
            source_sha256="a" * 64,
            reason="force_rebuild_current_manifest",
        )


class LifecycleCliTests(unittest.TestCase):
    def test_read_only_service_does_not_require_embedding_configuration(self):
        with (
            patch("app.lifecycle.cli.UniversalEmbeddingClient") as embedding_class,
            patch("app.lifecycle.cli.VectorStore"),
            patch("app.lifecycle.cli.DocumentRegistry"),
        ):
            service = _build_service(with_embedding=False)

        embedding_class.assert_not_called()
        embedding_class.configuration_for.assert_not_called()
        self.assertIsNone(service.embedding_client)

    def test_dry_run_service_uses_static_embedding_descriptor(self):
        with (
            patch("app.lifecycle.cli.UniversalEmbeddingClient") as embedding_class,
            patch("app.lifecycle.cli.VectorStore") as vector_store_class,
            patch("app.lifecycle.cli.DocumentRegistry") as registry_class,
        ):
            embedding_class.configuration_for.return_value = {
                "model": "configured-model",
                "dimensions": 8,
            }
            service = _build_service(
                with_embedding=False,
                with_manifest=True,
            )

        embedding_class.assert_not_called()
        embedding_class.configuration_for.assert_called_once()
        vector_store_class.assert_called_once()
        registry_class.assert_called_once()
        self.assertEqual(service.embedding_client.config["dimensions"], 8)

    def test_list_json(self):
        output = io.StringIO()
        with (
            patch("app.lifecycle.cli._build_service", return_value=FakeService()),
            redirect_stdout(output),
        ):
            status = main(["list", "--json"])

        self.assertEqual(status, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["documents"][0]["document_key"], "document-1")
        self.assertEqual(payload["vector_count"], 3)

    def test_rebuild_dry_run_json(self):
        output = io.StringIO()
        with (
            patch("app.lifecycle.cli._build_service", return_value=FakeService()),
            redirect_stdout(output),
        ):
            status = main(
                ["rebuild", "--document-key", "document-1", "--dry-run", "--json"]
            )

        self.assertEqual(status, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload[0]["planned_index_id"], "index-1")


if __name__ == "__main__":
    unittest.main()
