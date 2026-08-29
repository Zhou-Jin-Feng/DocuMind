import io
import json
import unittest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from app.api.main import create_app
from app.config import Settings
from app.lifecycle.models import DocumentDeletionResult, IngestionResult
from app.services.document_service import (
    DocumentDetail,
    DocumentIndexRecord,
    DocumentRecord,
)
from app.services.rag_service import ChatEvent
from app.services.retrieval_service import EvidenceChunk, RetrievalBatch
from app.services.retrieval_service import (
    DocumentIndexUnavailableError,
    DocumentNotFoundError,
    DocumentOperationInProgressError,
    RetrievalBusyError,
    RetrievalDependencyTimeoutError,
    StaleDocumentIndexError,
)


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


class FakeRetrievalService:
    def __init__(self):
        self.calls = []
        self.error = None
        self.empty = False

    def retrieve(self, query, **kwargs):
        self.calls.append((query, kwargs))
        if self.error is not None:
            raise self.error
        return RetrievalBatch(
            document_key="a" * 64,
            index_id="b" * 64,
            source_sha256="c" * 64,
            chunks=(
                ()
                if self.empty
                else (
                    EvidenceChunk(
                        chunk_id="d" * 64,
                        content="Full source evidence",
                        content_sha256="e" * 64,
                        source="paper.pdf",
                        page_number=3,
                        distance=0.42,
                        rank=1,
                    ),
                )
            ),
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
        self.retrieval_service = FakeRetrievalService()
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
                "retrieval": "ready",
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
                "retrieval": "unavailable",
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
        self.assertEqual(
            response.headers["content-type"], "text/event-stream; charset=utf-8"
        )
        self.assertIn("event: sources", response.text)
        self.assertIn('event: token\ndata: {"text":"回答"}', response.text)
        self.assertIn("event: done", response.text)
        self.assertEqual(self.application.rag_service.questions[0][0], "什么是 RAG？")

    def test_retrieve_returns_full_whitelisted_evidence_without_chat(self):
        chat_call_count = len(self.application.rag_service.questions)

        response = self.client.post(
            "/api/v1/retrieve",
            json={
                "schema_version": "1.0",
                "query": "supporting evidence",
                "document_key": "a" * 64,
                "expected_index_id": "b" * 64,
                "top_k": 3,
                "retrieval_mode": "dense",
                "distance_threshold": None,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["retrieval_version"], "dense-v1")
        self.assertEqual(payload["document_key"], "a" * 64)
        self.assertEqual(payload["chunks"][0]["content"], "Full source evidence")
        self.assertEqual(payload["chunks"][0]["source"], "paper.pdf")
        self.assertNotIn("metadata", payload["chunks"][0])
        self.assertEqual(
            len(self.application.rag_service.questions),
            chat_call_count,
        )
        self.assertEqual(
            self.application.retrieval_service.calls[-1][1]["expected_index_id"],
            "b" * 64,
        )

    def test_retrieve_records_safe_http_observation(self):
        metrics = Mock()
        with (
            patch("app.api.main.get_metrics", return_value=metrics),
            patch("app.api.main.logger") as logger,
        ):
            response = self.client.post(
                "/api/v1/retrieve",
                json=self._retrieve_request(),
                headers={
                    "X-Request-ID": "observation-request-1234",
                    "traceparent": (
                        "00-11111111111111111111111111111111-" "2222222222222222-01"
                    ),
                },
            )

        self.assertEqual(response.status_code, 200)
        metrics.record_pure_retrieval.assert_called_once()
        args = metrics.record_pure_retrieval.call_args.args
        self.assertEqual(args[:3], ("dense", 200, "none"))
        self.assertEqual(
            metrics.record_pure_retrieval.call_args.kwargs["result_count"],
            1,
        )
        fields = logger.info.call_args.kwargs
        self.assertEqual(fields["route"], "/api/v1/retrieve")
        self.assertEqual(fields["document_ref"], "a" * 12)
        self.assertEqual(fields["index_ref"], "b" * 12)
        serialized = repr(logger.info.call_args)
        self.assertNotIn("supporting evidence", serialized)
        self.assertNotIn("a" * 64, serialized)
        self.assertNotIn("Full source evidence", serialized)

    def test_retrieve_observes_validation_error_machine_code(self):
        metrics = Mock()
        with patch("app.api.main.get_metrics", return_value=metrics):
            response = self.client.post(
                "/api/v1/retrieve",
                json={**self._retrieve_request(), "top_k": 21},
            )

        self.assertEqual(response.status_code, 422)
        args = metrics.record_pure_retrieval.call_args.args
        self.assertEqual(args[:3], ("unknown", 422, "validation_error"))

    def test_retrieve_contract_is_published_in_openapi(self):
        openapi = self.client.get("/openapi.json").json()
        operation = openapi["paths"]["/api/v1/retrieve"]["post"]

        request_schema = operation["requestBody"]["content"]["application/json"][
            "schema"
        ]
        response_schema = operation["responses"]["200"]["content"]["application/json"][
            "schema"
        ]
        self.assertEqual(
            request_schema["$ref"],
            "#/components/schemas/RetrieveRequest",
        )
        self.assertEqual(
            response_schema["$ref"],
            "#/components/schemas/RetrieveResponse",
        )

    def test_retrieve_returns_successful_empty_chunk_list(self):
        self.application.retrieval_service.empty = True
        try:
            response = self.client.post(
                "/api/v1/retrieve",
                json=self._retrieve_request(),
            )
        finally:
            self.application.retrieval_service.empty = False

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["chunks"], [])

    def test_retrieve_maps_lifecycle_errors_to_stable_public_codes(self):
        cases = (
            (DocumentNotFoundError("document"), 404, "document_not_found"),
            (StaleDocumentIndexError("index"), 409, "stale_document_index"),
            (
                DocumentOperationInProgressError("document"),
                409,
                "document_operation_in_progress",
            ),
            (
                DocumentIndexUnavailableError("document"),
                409,
                "document_index_unavailable",
            ),
        )

        for error, status_code, code in cases:
            self.application.retrieval_service.error = error
            try:
                response = self.client.post(
                    "/api/v1/retrieve",
                    json=self._retrieve_request(),
                    headers={"X-Request-ID": "retrieve-request-1234"},
                )
            finally:
                self.application.retrieval_service.error = None

            with self.subTest(code=code):
                self.assertEqual(response.status_code, status_code)
                self.assertEqual(response.json()["error"]["code"], code)
                self.assertEqual(
                    response.json()["error"]["request_id"],
                    "retrieve-request-1234",
                )

    def test_retrieve_maps_dependency_failure_without_leaking_details(self):
        self.application.retrieval_service.error = ConnectionError(
            r"provider failed at C:\private\token.txt"
        )
        try:
            response = self.client.post(
                "/api/v1/retrieve",
                json=self._retrieve_request(),
            )
        finally:
            self.application.retrieval_service.error = None

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["error"]["code"],
            "retrieval_service_unavailable",
        )
        self.assertNotIn("private", response.text)
        self.assertNotIn("token.txt", response.text)

    def test_retrieve_maps_timeout_and_capacity_to_stable_codes(self):
        cases = (
            (RetrievalBusyError("busy"), "retrieval_capacity_exceeded"),
            (RetrievalDependencyTimeoutError("timeout"), "retrieval_timeout"),
        )
        for error, code in cases:
            self.application.retrieval_service.error = error
            try:
                response = self.client.post(
                    "/api/v1/retrieve",
                    json=self._retrieve_request(),
                )
            finally:
                self.application.retrieval_service.error = None
            with self.subTest(code=code):
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()["error"]["code"], code)

    def test_retrieve_uses_stable_503_when_service_is_not_ready(self):
        self.application.initialized = False
        try:
            response = self.client.post(
                "/api/v1/retrieve",
                json=self._retrieve_request(),
            )
        finally:
            self.application.initialized = True

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["error"]["code"],
            "retrieval_service_unavailable",
        )

    def test_retrieve_rejects_invalid_contract_with_public_422(self):
        response = self.client.post(
            "/api/v1/retrieve",
            json={**self._retrieve_request(), "top_k": 21},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "validation_error")
        self.assertNotIn("input", json.dumps(response.json(), ensure_ascii=False))

    def test_retrieve_rejects_oversized_request_before_validation(self):
        response = self.client.post(
            "/api/v1/retrieve",
            json={
                **self._retrieve_request(),
                "unexpected_padding": "x" * (17 * 1024),
            },
            headers={"X-Request-ID": "oversized-request-1234"},
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"]["code"], "request_too_large")
        self.assertEqual(
            response.json()["error"]["request_id"],
            "oversized-request-1234",
        )

    @staticmethod
    def _retrieve_request():
        return {
            "schema_version": "1.0",
            "query": "supporting evidence",
            "document_key": "a" * 64,
            "expected_index_id": "b" * 64,
            "top_k": 3,
            "retrieval_mode": "dense",
            "distance_threshold": None,
        }

    def test_invalid_question_has_public_error_shape(self):
        response = self.client.post("/api/v1/chat/stream", json={"question": "  "})
        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "validation_error")
        self.assertNotIn("input", json.dumps(payload, ensure_ascii=False))

    def test_upload_rejects_unsupported_extension(self):
        response = self.client.post(
            "/api/v1/documents",
            files={
                "file": ("legacy.doc", io.BytesIO(b"content"), "application/msword")
            },
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
