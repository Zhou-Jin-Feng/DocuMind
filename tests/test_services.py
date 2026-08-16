import unittest

from app.config import Settings
from app.core.retriever import RetrievalResult
from app.services.document_service import DocumentService
from app.services.rag_service import RAGService


class CapturingRetriever:
    def __init__(self, results=None):
        self.results = results or []
        self.calls = []

    def retrieve_semantic(self, question, **kwargs):
        self.calls.append((question, kwargs))
        return self.results


class CapturingGenerator:
    def __init__(self, chunks=None, error=None):
        self.chunks = chunks or []
        self.error = error

    def generate_answer_stream(self, question, results, config):
        for chunk in self.chunks:
            yield chunk
        if self.error:
            raise self.error


def result():
    return RetrievalResult(
        content="Milvus 保存 RAG 向量。",
        metadata={"source_file": "guide.txt", "page_number": 1, "chunk_id": "c1"},
        distance=0.2,
        rank=1,
    )


class RAGServiceTests(unittest.TestCase):
    @staticmethod
    def settings():
        return Settings(
            _env_file=None,
            default_llm_provider="openai",
            metrics_enabled=False,
        )

    def test_stream_emits_structured_success_events(self):
        retriever = CapturingRetriever([result()])
        service = RAGService(
            retriever=retriever,
            rag_generator=CapturingGenerator(["答", "案"]),
            settings=self.settings(),
        )

        events = list(service.stream_answer("Milvus 是什么？", request_id="req-1"))

        self.assertEqual(
            [event.type for event in events],
            ["status", "sources", "status", "token", "token", "done"],
        )
        self.assertEqual(events[1].data["items"][0]["chunk_id"], "c1")
        self.assertEqual(events[-1].data["status"], "success")
        self.assertEqual(retriever.calls[0][0], "Milvus 是什么？")

    def test_empty_context_emits_no_context_completion(self):
        service = RAGService(
            retriever=CapturingRetriever(),
            rag_generator=CapturingGenerator(["不会调用"]),
            settings=self.settings(),
        )

        events = list(service.stream_answer("没有资料的问题"))

        self.assertEqual(
            [event.type for event in events], ["status", "sources", "done"]
        )
        self.assertEqual(events[-1].data["status"], "no_context")

    def test_partial_generation_emits_public_interruption_error(self):
        service = RAGService(
            retriever=CapturingRetriever([result()]),
            rag_generator=CapturingGenerator(["部分"], RuntimeError("provider down")),
            settings=self.settings(),
        )

        events = list(service.stream_answer("请回答"))

        self.assertEqual(events[-1].type, "error")
        self.assertEqual(events[-1].data["code"], "generation_interrupted")
        self.assertTrue(events[-1].data["partial"])
        self.assertNotIn("provider down", events[-1].data["message"])


class DocumentServiceTests(unittest.TestCase):
    @staticmethod
    def registry():
        document = {
            "document_key": "doc-1",
            "tenant_id": "default",
            "collection_id": "rag_documents",
            "display_name": "guide.txt",
            "active_index_id": "index-1",
            "created_at": "2026-08-14T00:00:00+00:00",
            "updated_at": "2026-08-15T00:00:00+00:00",
        }
        indexes = (
            {
                "index_id": "index-1",
                "document_version_id": "version-1",
                "status": "active",
                "chunk_count": 3,
                "error_type": None,
                "file_type": ".txt",
                "file_size_bytes": 18,
                "source_sha256": "sha256-1",
                "created_at": "2026-08-14T00:00:00+00:00",
                "updated_at": "2026-08-14T00:01:00+00:00",
                "activated_at": "2026-08-14T00:01:00+00:00",
            },
            {
                "index_id": "index-2",
                "document_version_id": "version-2",
                "status": "failed",
                "chunk_count": 0,
                "error_type": "RuntimeError",
                "file_type": ".txt",
                "file_size_bytes": 24,
                "source_sha256": "sha256-2",
                "created_at": "2026-08-15T00:00:00+00:00",
                "updated_at": "2026-08-15T00:01:00+00:00",
                "activated_at": None,
            },
        )

        class Registry:
            @staticmethod
            def list_documents(**kwargs):
                del kwargs
                return (document,)

            @staticmethod
            def get_document(document_key):
                return document if document_key == "doc-1" else None

            @staticmethod
            def list_indexes(**kwargs):
                del kwargs
                return indexes

        return Registry()

    def service(self):
        return DocumentService(
            lifecycle_service=None,
            registry=self.registry(),
            tenant_id="default",
            collection_id="rag_documents",
        )

    def test_summary_keeps_active_index_and_exposes_latest_failure(self):
        summary = self.service().list_documents()[0]

        self.assertEqual(summary.status, "active")
        self.assertEqual(summary.active_version_id, "version-1")
        self.assertEqual(summary.version_count, 2)
        self.assertEqual(summary.error_type, "RuntimeError")

    def test_detail_orders_latest_index_first_and_numbers_versions(self):
        detail = self.service().get_document("doc-1")

        self.assertEqual(
            [index.document_version_id for index in detail.indexes],
            ["version-2", "version-1"],
        )
        self.assertEqual(
            [index.version_number for index in detail.indexes],
            [2, 1],
        )
        self.assertTrue(detail.indexes[1].is_active)


if __name__ == "__main__":
    unittest.main()
