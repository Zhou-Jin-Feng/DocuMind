import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.config import settings
from app.core.retriever import RetrievalResult
from web_app import RAGWebApp


class CapturingRetriever:
    def __init__(self, results=None, error=None):
        self.results = results or []
        self.error = error
        self.calls = []

    def retrieve_semantic(self, query, top_k, score_threshold=None):
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
        for chunk in self.chunks:
            yield chunk
        if self.error:
            raise self.error


class WebAppTests(unittest.TestCase):
    @staticmethod
    def _app(retriever, generator):
        app = RAGWebApp.__new__(RAGWebApp)
        app.initialized = True
        app.retriever = retriever
        app.rag_generator = generator
        return app

    @staticmethod
    def _result():
        return RetrievalResult(
            content="RAG通过检索文档增强回答。",
            metadata={"source_file": "guide.pdf", "page_number": 2},
            distance=0.25,
            rank=1,
            rerank_score=0.8,
        )

    def test_answer_uses_settings_and_formats_distance(self):
        retriever = CapturingRetriever([self._result()])
        generator = CapturingGenerator(["答", "案"])
        app = self._app(retriever, generator)

        outputs = list(app.answer_question(" 什么是RAG？ ", []))
        self.assertTrue(
            any("正在生成回答" in item[1][-1]["content"] for item in outputs)
        )
        final_history = outputs[-1][1]
        sources = outputs[-1][2]
        self.assertEqual(
            retriever.calls[0],
            (
                "什么是RAG？",
                settings.retrieval_top_k,
                settings.retrieval_score_threshold,
            ),
        )
        self.assertEqual(generator.config.temperature, settings.llm_temperature)
        self.assertEqual(generator.config.max_tokens, settings.llm_max_tokens)
        self.assertEqual(final_history[-1]["content"], "答案")
        self.assertIn("距离: 0.2500", sources)
        self.assertIn("第2页", sources)
        self.assertNotIn("相似度", sources)

    def test_sources_support_lexical_results_without_fake_distance(self):
        result = RetrievalResult(
            content="RRF 使用倒数排名融合。",
            metadata={"source_file": "retrieval.txt"},
            distance=None,
            rank=1,
            lexical_score=2.5,
            fusion_score=1 / 61,
        )

        sources = self._app(None, None)._format_sources([result])

        self.assertIn("BM25: 2.5000", sources)
        self.assertIn("RRF:", sources)
        self.assertNotIn("距离:", sources)

    def test_exception_does_not_duplicate_user_message(self):
        app = self._app(
            CapturingRetriever([self._result()]),
            CapturingGenerator(["部分回答"], RuntimeError("stream failed")),
        )
        outputs = list(app.answer_question("问题", []))
        final_history = outputs[-1][1]
        user_messages = [item for item in final_history if item["role"] == "user"]
        self.assertEqual(len(user_messages), 1)
        self.assertEqual(final_history[-1]["role"], "assistant")
        self.assertIn("部分回答", final_history[-1]["content"])
        self.assertIn("模型连接在流式生成过程中中断", final_history[-1]["content"])
        self.assertNotIn("stream failed", final_history[-1]["content"])
        self.assertIn("引用来源", outputs[-1][2])

    def test_retrieval_failure_is_not_reported_as_no_results(self):
        app = self._app(
            CapturingRetriever(error=RuntimeError("database down")),
            CapturingGenerator(),
        )
        outputs = list(app.answer_question("问题", []))
        self.assertIn("系统暂时无法", outputs[-1][1][-1]["content"])
        self.assertNotIn("未找到", outputs[-1][1][-1]["content"])

    def test_unsupported_upload_extension_is_rejected_before_processing(self):
        app = RAGWebApp.__new__(RAGWebApp)
        app.initialized = True
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "legacy.doc"
            file_path.write_bytes(b"content")
            message = app.upload_and_index_document(str(file_path))
        self.assertIn("不支持的文件格式", message)

    def test_persist_upload_uses_content_hash_and_original_extension(self):
        with (
            tempfile.TemporaryDirectory() as source_directory,
            tempfile.TemporaryDirectory() as upload_directory,
        ):
            source_path = Path(source_directory) / "原始名称.TXT"
            source_path.write_text("持久化测试", encoding="utf-8")

            persisted_path = RAGWebApp._persist_upload(source_path, upload_directory)

            self.assertEqual(persisted_path.parent, Path(upload_directory))
            self.assertEqual(persisted_path.suffix, ".txt")
            self.assertEqual(persisted_path.read_text(encoding="utf-8"), "持久化测试")
            self.assertEqual(len(persisted_path.stem), 64)

            second_path = RAGWebApp._persist_upload(source_path, upload_directory)
            self.assertEqual(second_path, persisted_path)

    def test_noop_upload_does_not_increment_chunk_metrics(self):
        app = RAGWebApp.__new__(RAGWebApp)
        app.lifecycle_service = SimpleNamespace(
            ingest=lambda *args, **kwargs: SimpleNamespace(
                status="noop",
                chunk_count=7,
                cleanup_pending=False,
                collection_count=7,
            )
        )
        metrics = SimpleNamespace(
            record_document_upload=lambda *args, **kwargs: None,
            record_document_ingestion=Mock(),
        )

        with patch("web_app.get_metrics", return_value=metrics):
            message = app._run_lifecycle_ingest(Path("guide.txt"), 10)

        self.assertIn("未重复构建", message)
        metrics.record_document_ingestion.assert_called_once()
        args, kwargs = metrics.record_document_ingestion.call_args
        self.assertEqual(args[0], "noop")
        self.assertEqual(kwargs["chunks_created"], 0)
        self.assertEqual(kwargs["chunks_indexed"], 0)


if __name__ == "__main__":
    unittest.main()
