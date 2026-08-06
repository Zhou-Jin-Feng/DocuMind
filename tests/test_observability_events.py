import io
import json
import tempfile
import unittest
from contextvars import Context
from pathlib import Path

from langchain_core.documents import Document

from app.core.retriever import Retriever
from app.core.retriever import RetrievalResult
from app.observability.logging import reset_logger, setup_logger
from web_app import RAGWebApp


class FakeEmbeddingClient:
    provider = "fake-embedding"

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


class FakeGenerator:
    def generate_answer_stream(self, query, results, config):
        yield "first"
        yield " token"


class FakeLoader:
    def load_document(self, path):
        return [Document(page_content="document content", metadata={})]


class FakeChunker:
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
        app = RAGWebApp.__new__(RAGWebApp)
        app.initialized = True
        app.llm_provider = "fake-llm"
        app.retriever = Retriever(FakeVectorStore(), FakeEmbeddingClient())
        app.rag_generator = FakeGenerator()
        private_query = "PRIVATE_QUERY_SHOULD_NOT_BE_LOGGED"

        outputs = list(app.answer_question(private_query, []))

        self.assertEqual(outputs[-1][1][-1]["content"], "first token")
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
            record["request_id"]
            for record in records
            if record["event"] in expected
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
        app = RAGWebApp.__new__(RAGWebApp)
        app.initialized = True
        app.llm_provider = "fake-llm"
        app.retriever = Retriever(FakeVectorStore(), FakeEmbeddingClient())
        app.rag_generator = FakeGenerator()

        stream = app.answer_question("question", [])
        outputs = []
        while True:
            try:
                outputs.append(Context().run(next, stream))
            except StopIteration:
                break

        self.assertEqual(outputs[-1][1][-1]["content"], "first token")
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

        app = RAGWebApp.__new__(RAGWebApp)
        app.initialized = True
        app.llm_provider = "fake-llm"
        app.retriever = Retriever(FakeVectorStore(), FakeEmbeddingClient())
        app.rag_generator = BrokenGenerator()

        stream = app.answer_question("question", [])
        outputs = []
        while True:
            try:
                outputs.append(Context().run(next, stream))
            except StopIteration:
                break

        final_answer = outputs[-1][1][-1]["content"]
        self.assertIn("partial answer", final_answer)
        self.assertIn("模型连接在流式生成过程中中断", final_answer)
        self.assertNotIn("private provider failure", final_answer)
        records = self._records()
        completion = next(
            record
            for record in records
            if record["event"] == "generation_completed"
        )
        response = next(
            record for record in records if record["event"] == "response_sent"
        )
        self.assertEqual(completion["status"], "error")
        self.assertEqual(response["status"], "error")
        self.assertEqual(completion["request_id"], response["request_id"])
        self.assertIsNotNone(response["request_id"])

    def test_document_ingestion_emits_stage_events_without_file_name(self):
        app = RAGWebApp.__new__(RAGWebApp)
        app.initialized = True
        app.embedding_provider = "fake-embedding"
        app.doc_loader = FakeLoader()
        app.chunker = FakeChunker()
        app.embedding_client = FakeEmbeddingClient()
        app.vector_store = FakeVectorStore()

        with tempfile.TemporaryDirectory() as directory:
            file_name = "private-customer-name.txt"
            file_path = Path(directory) / file_name
            file_path.write_text("content", encoding="utf-8")
            result = app.upload_and_index_document(str(file_path))

        self.assertIn("文档处理完成", result)
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
            record["request_id"]
            for record in records
            if record["event"] in expected
        }
        self.assertEqual(len(request_ids), 1)
        self.assertNotIn(file_name, self.console.getvalue())


if __name__ == "__main__":
    unittest.main()
