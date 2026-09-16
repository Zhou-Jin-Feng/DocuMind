import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from app.config import Settings
from app.core.retriever import RetrievalResult
from app.lifecycle.service import DocumentLifecycleService
from app.services.document_service import DocumentService
from app.services.rag_service import RAGService, SourceReference


class CapturingRetriever:
    def __init__(self, results=None, error=None):
        self.results = results or []
        self.error = error
        self.calls = []

    def retrieve_semantic(self, query, top_k, score_threshold=None, **kwargs):
        self.calls.append((query, top_k, score_threshold))
        if self.error:
            raise self.error
        return self.results


class CapturingGenerator:
    def __init__(self, chunks=None, error=None):
        self.chunks = chunks or []
        self.error = error
        self.config = None

    def generate_answer_stream(self, query, results, config):
        self.config = config
        yield from self.chunks
        if self.error:
            raise self.error


class ServiceRegressionTests(unittest.TestCase):
    @staticmethod
    def settings():
        return Settings(
            _env_file=None, default_llm_provider="openai", metrics_enabled=False
        )

    @staticmethod
    def result():
        return RetrievalResult(
            content="RAG通过检索文档增强回答。",
            metadata={"source_file": "guide.pdf", "page_number": 2},
            distance=0.25,
            rank=1,
            rerank_score=0.8,
        )

    def test_answer_uses_settings_and_preserves_source_fields(self):
        retriever = CapturingRetriever([self.result()])
        generator = CapturingGenerator(["答", "案"])
        settings = self.settings()
        service = RAGService(
            retriever=retriever, rag_generator=generator, settings=settings
        )
        events = list(service.stream_answer(" 什么是RAG？ "))
        self.assertEqual(
            retriever.calls,
            [
                (
                    "什么是RAG？",
                    settings.retrieval_top_k,
                    settings.retrieval_score_threshold,
                )
            ],
        )
        self.assertEqual(generator.config.temperature, settings.llm_temperature)
        self.assertEqual(generator.config.max_tokens, settings.llm_max_tokens)
        self.assertEqual(
            "".join(e.data["text"] for e in events if e.type == "token"), "答案"
        )
        sources = next(e.data["items"] for e in events if e.type == "sources")
        self.assertEqual(sources[0]["distance"], 0.25)
        self.assertEqual(sources[0]["page_number"], 2)
        self.assertEqual(sources[0]["rerank_score"], 0.8)
        self.assertEqual(events[-1].type, "done")

    def test_lexical_source_has_no_fabricated_distance(self):
        result = RetrievalResult(
            content="RRF 使用倒数排名融合。",
            metadata={"source_file": "retrieval.txt"},
            distance=None,
            rank=1,
            lexical_score=2.5,
            fusion_score=1 / 61,
        )
        source = SourceReference.from_result(result).to_dict()
        self.assertIsNone(source["distance"])
        self.assertEqual(source["lexical_score"], 2.5)
        self.assertEqual(source["fusion_score"], 1 / 61)

    def test_partial_failure_has_one_terminal_error_and_keeps_tokens(self):
        service = RAGService(
            retriever=CapturingRetriever([self.result()]),
            rag_generator=CapturingGenerator(
                ["部分回答"], RuntimeError("private provider failure")
            ),
            settings=self.settings(),
        )
        events = list(service.stream_answer("问题"))
        self.assertEqual(
            "".join(e.data["text"] for e in events if e.type == "token"), "部分回答"
        )
        self.assertEqual(sum(e.type == "error" for e in events), 1)
        self.assertFalse(any(e.type == "done" for e in events))
        self.assertEqual(events[-1].data["code"], "generation_interrupted")
        self.assertNotIn("private provider failure", events[-1].data["message"])

    def test_retrieval_failure_is_not_no_context(self):
        generator = CapturingGenerator()
        service = RAGService(
            retriever=CapturingRetriever(
                error=RuntimeError("private database failure")
            ),
            rag_generator=generator,
            settings=self.settings(),
        )
        events = list(service.stream_answer("问题"))
        self.assertEqual(events[-1].type, "error")
        self.assertEqual(events[-1].data["code"], "service_unavailable")
        self.assertFalse(any(e.type == "done" for e in events))
        self.assertNotIn("private database failure", repr([e.data for e in events]))
        self.assertIsNone(generator.config)

    def test_persist_upload_uses_content_hash_and_original_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "原始名称.TXT"
            original.write_text("持久化测试", encoding="utf-8")
            dest = root / "uploads"
            persisted = DocumentLifecycleService.persist_source_file(
                original, str(dest)
            )
            self.assertEqual(persisted.parent, dest)
            self.assertEqual(persisted.suffix, ".txt")
            self.assertEqual(len(persisted.stem), 64)
            self.assertEqual(persisted.read_text(encoding="utf-8"), "持久化测试")
            self.assertEqual(
                DocumentLifecycleService.persist_source_file(original, str(dest)),
                persisted,
            )

    def test_noop_upload_does_not_increment_chunk_metrics(self):
        lifecycle = Mock()
        lifecycle.ingest.return_value = SimpleNamespace(status="noop", chunk_count=7)
        metrics = Mock()
        service = DocumentService(
            lifecycle_service=lifecycle,
            registry=None,
            tenant_id="default",
            collection_id="rag_documents",
            metrics_getter=lambda: metrics,
        )
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "guide.txt"
            source.write_text("content", encoding="utf-8")
            result = service.ingest(source, display_name=source.name)
        self.assertEqual(result.status, "noop")
        metrics.record_document_upload.assert_called_once_with("accepted")
        metrics.record_document_ingestion.assert_called_once()
        args, kwargs = metrics.record_document_ingestion.call_args
        self.assertEqual(args[0], "noop")
        self.assertEqual(kwargs["chunks_created"], 0)
        self.assertEqual(kwargs["chunks_indexed"], 0)

    def test_api_import_does_not_require_gradio(self):
        script = """
import importlib.abc
import sys
sys.path.insert(0, sys.argv[1])
class DenyGradio(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'gradio' or fullname.startswith('gradio.'):
            raise ImportError('Gradio must not be a runtime dependency')
sys.meta_path.insert(0, DenyGradio())
from app.api.main import create_app
assert callable(create_app)
assert not any(n == 'gradio' or n.startswith('gradio.') for n in sys.modules)
"""
        result = subprocess.run(
            [sys.executable, "-c", script, str(Path(__file__).resolve().parents[1])],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
