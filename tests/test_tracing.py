import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.documents import Document
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import StatusCode

from app.core.retriever import Retriever
from app.core.retriever import RetrievalResult
from app.lifecycle.registry import DocumentRegistry
from app.lifecycle.service import DocumentLifecycleService
from app.observability.context import get_trace_id, request_context
from web_app import RAGWebApp
from app.observability.logging import get_logger, reset_logger, setup_logger
from app.observability.tracing import (
    configure_tracing,
    shutdown_tracing,
    trace_span,
)


class FakeEmbeddingClient:
    provider = "fake-embedding"
    config = {"model": "fake-model", "dimensions": 2}

    def embed_text(self, text):
        return [0.1, 0.2]

    def embed_texts_batch(self, texts, show_progress=False):
        return [[0.1, 0.2] for _ in texts]


class FailingEmbeddingClient(FakeEmbeddingClient):
    def embed_text(self, text):
        raise RuntimeError("private provider failure")


class FakeVectorStore:
    class Collection:
        @staticmethod
        def count():
            return 2

    def __init__(self):
        self.collection = self.Collection()

    def search(self, query_embedding, n_results, where=None):
        return {
            "documents": ["retrieved private content"],
            "metadatas": [{"source_file": "private-guide.txt"}],
            "distances": [0.2],
        }

    def add_documents(self, chunks, embeddings):
        return ["chunk-1", "chunk-2"]

    def count_by_index_id(self, index_id):
        return 2

    def delete_by_index_id(self, index_id):
        return None


class FakeLoader:
    def load_document(self, path):
        return [Document(page_content="private document content", metadata={})]


class FakeChunker:
    chunk_size = 500
    chunk_overlap = 100

    def chunk_documents_recursive(self, documents):
        return [
            Document(page_content="private chunk one", metadata={"chunk_id": "1"}),
            Document(page_content="private chunk two", metadata={"chunk_id": "2"}),
        ]


class FakeGenerator:
    def generate_answer_stream(self, query, results, config):
        yield "safe"
        yield " answer"


class TracingTests(unittest.TestCase):
    def tearDown(self):
        shutdown_tracing()
        reset_logger()

    def test_disabled_tracing_is_noop(self):
        configure_tracing(False)
        with request_context(trace_id="fallback-trace"):
            with trace_span("rag.query") as span:
                self.assertFalse(span.is_recording())
                self.assertEqual(get_trace_id(), "fallback-trace")

    def test_no_endpoint_does_not_construct_otlp_exporter(self):
        with patch("app.observability.tracing.OTLPSpanExporter") as exporter_cls:
            configure_tracing(True, endpoint=None)
            with trace_span("rag.query"):
                pass
        exporter_cls.assert_not_called()

    def test_endpoint_uses_otlp_exporter_with_batch_processor(self):
        with patch("app.observability.tracing.OTLPSpanExporter") as exporter_cls, patch(
            "app.observability.tracing.BatchSpanProcessor"
        ) as processor_cls:
            configure_tracing(
                True,
                endpoint="http://127.0.0.1:4318/v1/traces",
            )

        exporter_cls.assert_called_once_with(
            endpoint="http://127.0.0.1:4318/v1/traces"
        )
        processor_cls.assert_called_once_with(exporter_cls.return_value)

    def test_in_memory_exporter_receives_parent_child_spans(self):
        exporter = InMemorySpanExporter()
        configure_tracing(True, span_exporter=exporter)

        with trace_span("rag.query"):
            with trace_span("rag.retrieve"):
                with trace_span("embedding.query"):
                    pass

        spans = {span.name: span for span in exporter.get_finished_spans()}
        self.assertEqual(set(spans), {"rag.query", "rag.retrieve", "embedding.query"})
        self.assertEqual(
            spans["rag.retrieve"].parent.span_id,
            spans["rag.query"].context.span_id,
        )
        self.assertEqual(
            spans["embedding.query"].parent.span_id,
            spans["rag.retrieve"].context.span_id,
        )
        self.assertEqual(
            spans["rag.query"].context.trace_id,
            spans["embedding.query"].context.trace_id,
        )

    def test_log_trace_id_matches_exported_span(self):
        exporter = InMemorySpanExporter()
        configure_tracing(True, span_exporter=exporter)
        console = io.StringIO()

        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "rag.jsonl"
            setup_logger(log_file_path=log_path, console_sink=console)
            with request_context(request_id="req-trace-test"):
                with trace_span("rag.query") as span:
                    get_logger(__name__).info(
                        "trace correlation",
                        event="trace_correlation_test",
                        operation="rag.query",
                    )
                    expected_trace_id = format(
                        span.get_span_context().trace_id,
                        "032x",
                    )
            reset_logger()
            records = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
            ]

        record = next(
            item for item in records if item["event"] == "trace_correlation_test"
        )
        self.assertEqual(record["trace_id"], expected_trace_id)
        self.assertEqual(record["request_id"], "req-trace-test")

    def test_exception_marks_error_without_message_or_exception_event(self):
        exporter = InMemorySpanExporter()
        configure_tracing(True, span_exporter=exporter)
        secret_message = "api_key=sk-do-not-export"

        with self.assertRaises(RuntimeError):
            with trace_span("embedding.query"):
                raise RuntimeError(secret_message)

        span = exporter.get_finished_spans()[0]
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(dict(span.attributes), {"error.type": "RuntimeError"})
        self.assertEqual(tuple(span.events), ())
        self.assertNotIn(secret_message, repr(span))

    def test_sensitive_span_attributes_are_dropped(self):
        exporter = InMemorySpanExporter()
        configure_tracing(True, span_exporter=exporter)
        secret = "sk-span-secret"

        with trace_span(
            "rag.query",
            attributes={
                "provider": "test",
                "query_text": "private question",
                "file_name": "private.pdf",
                "api_key": secret,
                "authorization": f"Bearer {secret}",
            },
        ):
            pass

        attributes = dict(exporter.get_finished_spans()[0].attributes)
        self.assertEqual(attributes, {"provider": "test"})
        self.assertNotIn(secret, repr(attributes))

    def test_reconfiguration_does_not_replace_global_provider(self):
        global_provider = trace.get_tracer_provider()
        first_exporter = InMemorySpanExporter()
        second_exporter = InMemorySpanExporter()

        configure_tracing(True, span_exporter=first_exporter)
        configure_tracing(True, span_exporter=second_exporter)

        self.assertIs(trace.get_tracer_provider(), global_provider)
        with trace_span("rag.query"):
            pass
        self.assertEqual(len(second_exporter.get_finished_spans()), 1)


    def test_real_query_pipeline_emits_expected_span_tree(self):
        exporter = InMemorySpanExporter()
        configure_tracing(True, span_exporter=exporter)
        app = RAGWebApp.__new__(RAGWebApp)
        app.initialized = True
        app.llm_provider = "fake-llm"
        app.retriever = Retriever(FakeVectorStore(), FakeEmbeddingClient())
        app.rag_generator = FakeGenerator()

        outputs = list(app.answer_question("private question", []))

        self.assertEqual(outputs[-1][1][-1]["content"], "safe answer")
        spans = {span.name: span for span in exporter.get_finished_spans()}
        expected_names = {
            "rag.query",
            "rag.retrieve",
            "embedding.query",
            "vector.search",
            "rag.context.build",
            "llm.generate",
        }
        self.assertEqual(set(spans), expected_names)
        root = spans["rag.query"]
        self.assertEqual(spans["rag.retrieve"].parent.span_id, root.context.span_id)
        self.assertEqual(
            spans["embedding.query"].parent.span_id,
            spans["rag.retrieve"].context.span_id,
        )
        self.assertEqual(
            spans["vector.search"].parent.span_id,
            spans["rag.retrieve"].context.span_id,
        )
        self.assertEqual(
            spans["rag.context.build"].parent.span_id,
            root.context.span_id,
        )
        self.assertEqual(spans["llm.generate"].parent.span_id, root.context.span_id)
        serialized = repr([dict(span.attributes) for span in spans.values()])
        self.assertNotIn("private question", serialized)
        self.assertNotIn("private-guide.txt", serialized)
        self.assertNotIn("retrieved private content", serialized)

    def test_document_ingestion_emits_expected_span_tree(self):
        exporter = InMemorySpanExporter()
        configure_tracing(True, span_exporter=exporter)
        app = RAGWebApp.__new__(RAGWebApp)
        app.initialized = True
        app.embedding_provider = "fake-embedding"
        app.doc_loader = FakeLoader()
        app.chunker = FakeChunker()
        app.embedding_client = FakeEmbeddingClient()
        app.vector_store = FakeVectorStore()

        with tempfile.TemporaryDirectory() as directory:
            app.registry = DocumentRegistry(str(Path(directory) / "registry.sqlite3"))
            app.lifecycle_service = DocumentLifecycleService(
                loader=app.doc_loader,
                chunker=app.chunker,
                embedding_client=app.embedding_client,
                vector_store=app.vector_store,
                registry=app.registry,
                upload_dir=str(Path(directory) / "uploads"),
            )
            private_name = "private-customer-name.txt"
            file_path = Path(directory) / private_name
            file_path.write_text("private upload content", encoding="utf-8")
            result = app.upload_and_index_document(str(file_path))

        self.assertIn("文档处理完成", result)
        spans = {span.name: span for span in exporter.get_finished_spans()}
        expected_names = {
            "rag.document.ingest",
            "document.load",
            "document.chunk",
            "embedding.batch",
            "vector.upsert",
        }
        self.assertEqual(set(spans), expected_names)
        root = spans["rag.document.ingest"]
        for child_name in expected_names - {"rag.document.ingest"}:
            self.assertEqual(spans[child_name].parent.span_id, root.context.span_id)
        serialized = repr([dict(span.attributes) for span in spans.values()])
        self.assertNotIn(private_name, serialized)
        self.assertNotIn("private upload content", serialized)
        self.assertNotIn("private document content", serialized)

    def test_embedding_failure_marks_child_and_retrieval_spans_error(self):
        exporter = InMemorySpanExporter()
        configure_tracing(True, span_exporter=exporter)
        retriever = Retriever(FakeVectorStore(), FailingEmbeddingClient())

        with self.assertRaises(RuntimeError):
            retriever.retrieve_semantic("private question")

        spans = {span.name: span for span in exporter.get_finished_spans()}
        self.assertEqual(spans["embedding.query"].status.status_code, StatusCode.ERROR)
        self.assertEqual(spans["rag.retrieve"].status.status_code, StatusCode.ERROR)
        self.assertEqual(
            spans["embedding.query"].attributes["error.type"],
            "RuntimeError",
        )
        self.assertEqual(spans["rag.retrieve"].attributes["error.type"], "RuntimeError")
        for span in spans.values():
            self.assertEqual(tuple(span.events), ())
            self.assertNotIn("private provider failure", repr(span.attributes))


if __name__ == "__main__":
    unittest.main()
