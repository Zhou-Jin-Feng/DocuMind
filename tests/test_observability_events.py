import io
import json
import tempfile
import unittest
from contextvars import Context
from pathlib import Path

from langchain_core.documents import Document

from app.core.retriever import Retriever
from app.core.retriever import RetrievalResult
from app.lifecycle.registry import DocumentRegistry
from app.lifecycle.service import DocumentLifecycleService
from app.observability.logging import reset_logger, setup_logger
from app.config import Settings
from app.services.rag_service import RAGService
from app.services.document_service import DocumentService
from app.observability.context import request_context


class FakeEmbeddingClient:
    provider = "fake-embedding"
    config = {"model": "fake-model", "dimensions": 2}

    def embed_text(self, text):
        return [0.1, 0.2]

    def embed_texts_batch(self, texts, show_progress=False):
        return [[0.1, 0.2] for _ in texts]


class FakeVectorStore:
    class Collection:
        @staticmethod
        def count():
            return 2

    def __init__(self):
        self.collection = self.Collection()
        self.added = []

    def search(self, query_embedding, n_results, where=None):
        return {
            "documents": ["RAG uses retrieved context."],
            "metadatas": [{"source_file": "guide.txt"}],
            "distances": [0.2],
        }

    def add_documents(self, chunks, embeddings):
        self.added.append((chunks, embeddings))
        return ["chunk-1", "chunk-2"]

    def count(self):
        return self.collection.count()

    def count_by_index_id(self, index_id):
        return 2

    def delete_by_index_id(self, index_id):
        return None


class FakeGenerator:
    def generate_answer_stream(self, query, results, config):
        yield "first"
        yield " token"


class FakeLoader:
    def load_document(self, path):
        return [Document(page_content="document content", metadata={})]


class FakeChunker:
    chunk_size = 500
    chunk_overlap = 100

    def chunk_documents_recursive(self, documents):
        return [
            Document(page_content="chunk one", metadata={"chunk_id": "1"}),
            Document(page_content="chunk two", metadata={"chunk_id": "2"}),
        ]


class ObservabilityEventTests(unittest.TestCase):
    def setUp(self):
        self.console = io.StringIO()
        setup_logger(
            log_file_path=None,
            console_sink=self.console,
            console_format="json",
            service="rag-test",
            environment="test",
        )
        self.console.seek(0)
        self.console.truncate(0)

    def tearDown(self):
        reset_logger()

    def _records(self):
        return [
            json.loads(line)
            for line in self.console.getvalue().splitlines()
            if line.strip()
        ]

    def test_query_stream_emits_ordered_events_with_one_request_id(self):
        service = RAGService(
            retriever=Retriever(FakeVectorStore(), FakeEmbeddingClient()),
            rag_generator=FakeGenerator(),
            settings=Settings(
                _env_file=None, default_llm_provider="openai", metrics_enabled=False
            ),
        )
        private_query = "PRIVATE_QUERY_SHOULD_NOT_BE_LOGGED"

        outputs = list(service.stream_answer(private_query))

        self.assertEqual(
            "".join(event.data["text"] for event in outputs if event.type == "token"),
            "first token",
        )
        records = self._records()
        events = [record["event"] for record in records]
        expected = [
            "query_received",
            "retrieval_started",
            "query_embedding_completed",
            "retrieval_completed",
            "context_built",
            "generation_started",
            "first_token_received",
            "generation_completed",
            "response_sent",
        ]
        positions = [events.index(event) for event in expected]
        self.assertEqual(positions, sorted(positions))

        request_ids = {
            record["request_id"] for record in records if record["event"] in expected
        }
        self.assertEqual(len(request_ids), 1)
        self.assertNotIn(private_query, self.console.getvalue())
        for record in records:
            if record["event"] in {
                "query_embedding_completed",
                "retrieval_completed",
                "context_built",
                "first_token_received",
                "generation_completed",
                "response_sent",
            }:
                self.assertIsInstance(record["duration_ms"], (int, float))

    def test_query_context_survives_resume_in_different_contexts(self):
        service = RAGService(
            retriever=Retriever(FakeVectorStore(), FakeEmbeddingClient()),
            rag_generator=FakeGenerator(),
            settings=Settings(
                _env_file=None, default_llm_provider="openai", metrics_enabled=False
            ),
        )

        stream = service.stream_answer("question")
        outputs = []
        while True:
            try:
                outputs.append(Context().run(next, stream))
            except StopIteration:
                break

        self.assertEqual(
            "".join(event.data["text"] for event in outputs if event.type == "token"),
            "first token",
        )
        records = self._records()
        tracked_events = {
            "query_received",
            "retrieval_started",
            "query_embedding_completed",
            "retrieval_completed",
            "context_built",
            "generation_started",
            "first_token_received",
            "generation_completed",
            "response_sent",
        }
        tracked_records = [
            record for record in records if record["event"] in tracked_events
        ]
        request_ids = {record["request_id"] for record in tracked_records}
        trace_ids = {record["trace_id"] for record in tracked_records}
        self.assertEqual(len(request_ids), 1)
        self.assertNotIn(None, request_ids)
        self.assertEqual(len(trace_ids), 1)
        self.assertNotIn(None, trace_ids)

    def test_stream_error_closes_event_chain_and_preserves_partial_answer(self):
        class BrokenGenerator:
            def generate_answer_stream(self, query, results, config):
                yield "partial answer"
                raise RuntimeError("private provider failure")

        service = RAGService(
            retriever=Retriever(FakeVectorStore(), FakeEmbeddingClient()),
            rag_generator=BrokenGenerator(),
            settings=Settings(
                _env_file=None, default_llm_provider="openai", metrics_enabled=False
            ),
        )

        stream = service.stream_answer("question")
        outputs = []
        while True:
            try:
                outputs.append(Context().run(next, stream))
            except StopIteration:
                break

        final_answer = "".join(
            event.data["text"] for event in outputs if event.type == "token"
        )
        self.assertIn("partial answer", final_answer)
        self.assertEqual(outputs[-1].type, "error")
        self.assertIn("模型连接在流式生成过程中中断", outputs[-1].data["message"])
        self.assertTrue(outputs[-1].data["partial"])
        self.assertEqual(sum(event.type == "error" for event in outputs), 1)
        self.assertFalse(any(event.type == "done" for event in outputs))
        self.assertNotIn("private provider failure", final_answer)
        records = self._records()
        completion = next(
            record for record in records if record["event"] == "generation_completed"
        )
        response = next(
            record for record in records if record["event"] == "response_sent"
        )
        self.assertEqual(
            sum(record["event"] == "generation_completed" for record in records), 1
        )
        self.assertEqual(completion["status"], "error")
        self.assertEqual(response["status"], "error")
        self.assertEqual(completion["request_id"], response["request_id"])
        self.assertIsNotNone(response["request_id"])

    def test_document_ingestion_emits_stage_events_without_file_name(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = DocumentRegistry(str(Path(directory) / "registry.sqlite3"))
            lifecycle = DocumentLifecycleService(
                loader=FakeLoader(),
                chunker=FakeChunker(),
                embedding_client=FakeEmbeddingClient(),
                vector_store=FakeVectorStore(),
                registry=registry,
                upload_dir=str(Path(directory) / "uploads"),
            )
            file_name = "private-customer-name.txt"
            file_path = Path(directory) / file_name
            file_path.write_text("content", encoding="utf-8")
            service = DocumentService(
                lifecycle_service=lifecycle,
                registry=registry,
                tenant_id="default",
                collection_id="rag_documents",
            )
            with request_context(request_id="ingestion-test"):
                result = service.ingest(file_path, display_name=file_path.name)

        self.assertEqual(result.status, "indexed")
        records = self._records()
        events = [record["event"] for record in records]
        expected = [
            "document_upload_received",
            "document_loaded",
            "document_chunked",
            "document_embedding_completed",
            "vector_upsert_completed",
            "document_indexing_completed",
        ]
        positions = [events.index(event) for event in expected]
        self.assertEqual(positions, sorted(positions))
        request_ids = {
            record["request_id"] for record in records if record["event"] in expected
        }
        self.assertEqual(len(request_ids), 1)
        self.assertNotIn(file_name, self.console.getvalue())


if __name__ == "__main__":
    unittest.main()
