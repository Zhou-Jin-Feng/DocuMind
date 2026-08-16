import io
import json
import unittest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.config import Settings
from app.lifecycle.models import DocumentDeletionResult, IngestionResult
from app.services.document_service import (
    DocumentDetail,
    DocumentIndexRecord,
    DocumentRecord,
)
from app.services.rag_service import ChatEvent


class FakeRAGService:
    def __init__(self):
        self.questions = []

    def stream_answer(self, question, *, request_id=None):
        self.questions.append((question, request_id))
        yield ChatEvent("status", {"stage": "retrieving"})
        yield ChatEvent(
            "sources",
            {
                "items": [
                    {
                        "rank": 1,
                        "source": "guide.txt",
                        "page_number": None,
                        "excerpt": "RAG source",
                    }
                ]
            },
        )
        yield ChatEvent("token", {"text": "回答"})
        yield ChatEvent("done", {"status": "success"})


class FakeDocumentService:
    def __init__(self):
        self.ingested = []

    def list_documents(self):
        return (
            DocumentRecord(
                document_key="doc-1",
                display_name="guide.txt",
                status="active",
                chunk_count=3,
                file_type=".txt",
                file_size_bytes=18,
                active_index_id="index-1",
                active_version_id="version-1",
                version_count=1,
                error_type=None,
                created_at="2026-08-14T00:00:00+00:00",
                updated_at="2026-08-14T00:00:00+00:00",
            ),
        )

    def get_document(self, document_key):
        if document_key != "doc-1":
            raise KeyError(document_key)
        summary = self.list_documents()[0]
        return DocumentDetail(
            summary=summary,
            indexes=(
                DocumentIndexRecord(
                    index_id="index-1",
                    document_version_id="version-1",
                    version_number=1,
                    status="active",
                    chunk_count=3,
                    error_type=None,
                    file_type=".txt",
                    file_size_bytes=18,
                    source_sha256="sha256",
                    created_at="2026-08-14T00:00:00+00:00",
                    updated_at="2026-08-14T00:00:00+00:00",
                    activated_at="2026-08-14T00:00:00+00:00",
                    is_active=True,
                ),
            ),
        )

    def ingest(self, source_path, *, display_name):
        self.ingested.append((source_path, display_name))
        return IngestionResult(
            status="success",
            operation_id="operation-1",
            document_key="doc-1",
            document_version_id="version-1",
            index_id="index-1",
            source_sha256="sha256",
            chunk_count=3,
            collection_count=3,
        )

    def reindex(self, document_key):
        if document_key != "doc-1":
            raise KeyError(document_key)
        return self.ingest("persisted-source", display_name="guide.txt")

    def delete(self, document_key):
        if document_key != "doc-1":
            raise KeyError(document_key)
        return DocumentDeletionResult(
            status="deleted",
            document_key=document_key,
            deleted_index_count=1,
            deleted_chunk_count=3,
            collection_count=0,
        )


class FakeApplication:
    def __init__(self):
        self.settings = Settings(
            _env_file=None,
            metrics_enabled=False,
            api_cors_origins=["http://localhost:5173"],
        )
        self.initialized = True
        self.rag_service = FakeRAGService()
        self.document_service = FakeDocumentService()

    def readiness(self):
        return {
            "status": "ready",
            "ready": True,
            "components": {
                "application": "ready",
                "milvus": "ready",
                "embedding": "ready",
                "llm": "ready",
                "registry": "ready",
            },
            "error_type": None,
        }


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = FakeApplication()
        cls.client_context = TestClient(
            create_app(cls.application, configure_runtime=False)
        )
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)

    def test_liveness_readiness_and_request_id(self):
        live = self.client.get("/api/v1/health/live")
        self.assertEqual(live.status_code, 200)
        self.assertEqual(live.json()["status"], "alive")
        self.assertRegex(live.headers["X-Request-ID"], r"^[a-f0-9]{32}$")

        ready = self.client.get("/api/v1/health/ready")
        self.assertEqual(ready.status_code, 200)
        self.assertTrue(ready.json()["ready"])

    def test_readiness_returns_503_when_dependency_is_unavailable(self):
        original_readiness = self.application.readiness
        self.application.readiness = lambda: {
            "status": "degraded",
            "ready": False,
            "components": {
                "application": "ready",
                "milvus": "unavailable",
                "embedding": "ready",
                "llm": "ready",
                "registry": "ready",
            },
            "error_type": "dependency_unavailable",
        }
        try:
            response = self.client.get("/api/v1/health/ready")
        finally:
            self.application.readiness = original_readiness

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertFalse(response.json()["ready"])
        self.assertEqual(response.json()["error_type"], "dependency_unavailable")

    def test_documents_are_structured(self):
        response = self.client.get("/api/v1/documents")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(response.json()["items"][0]["status"], "active")
        self.assertEqual(response.json()["items"][0]["version_count"], 1)

    def test_document_detail_includes_index_history(self):
        response = self.client.get("/api/v1/documents/doc-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["active_version_id"], "version-1")
        self.assertTrue(response.json()["indexes"][0]["is_active"])

    def test_document_detail_returns_public_not_found_error(self):
        response = self.client.get("/api/v1/documents/missing")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "document_not_found")

    def test_chat_stream_emits_sse_events(self):
        response = self.client.post(
            "/api/v1/chat/stream",
            json={"question": "什么是 RAG？"},
            headers={"X-Request-ID": "test-request-1234"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "text/event-stream; charset=utf-8")
        self.assertIn("event: sources", response.text)
        self.assertIn('event: token\ndata: {"text":"回答"}', response.text)
        self.assertIn("event: done", response.text)
        self.assertEqual(self.application.rag_service.questions[0][0], "什么是 RAG？")

    def test_invalid_question_has_public_error_shape(self):
        response = self.client.post("/api/v1/chat/stream", json={"question": "  "})
        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "validation_error")
        self.assertNotIn("input", json.dumps(payload, ensure_ascii=False))

    def test_upload_rejects_unsupported_extension(self):
        response = self.client.post(
            "/api/v1/documents",
            files={"file": ("legacy.doc", io.BytesIO(b"content"), "application/msword")},
        )
        self.assertEqual(response.status_code, 415)
        self.assertEqual(response.json()["error"]["code"], "unsupported_file_type")

    def test_upload_returns_ingestion_contract_and_cors(self):
        response = self.client.post(
            "/api/v1/documents",
            files={"file": ("guide.txt", io.BytesIO(b"content"), "text/plain")},
            headers={"Origin": "http://localhost:5173"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["chunk_count"], 3)
        self.assertEqual(
            response.headers["access-control-allow-origin"], "http://localhost:5173"
        )

    def test_reindex_and_delete_return_structured_results(self):
        reindexed = self.client.post("/api/v1/documents/doc-1/reindex")
        deleted = self.client.delete("/api/v1/documents/doc-1")

        self.assertEqual(reindexed.status_code, 200)
        self.assertEqual(reindexed.json()["index_id"], "index-1")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["deleted_chunk_count"], 3)

    def test_document_delete_is_allowed_by_cors_preflight(self):
        response = self.client.options(
            "/api/v1/documents/doc-1",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "DELETE",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("DELETE", response.headers["access-control-allow-methods"])


if __name__ == "__main__":
    unittest.main()
