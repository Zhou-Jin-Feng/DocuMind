import tempfile
import unittest
from pathlib import Path

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
        final_history = outputs[-1][1]
        sources = outputs[-1][2]
        self.assertEqual(
            retriever.calls[0],
            ("什么是RAG？", settings.retrieval_top_k, settings.retrieval_score_threshold),
        )
        self.assertEqual(generator.config.temperature, settings.llm_temperature)
        self.assertEqual(generator.config.max_tokens, settings.llm_max_tokens)
        self.assertEqual(final_history[-1]["content"], "答案")
        self.assertIn("距离: 0.2500", sources)
        self.assertIn("第2页", sources)
        self.assertNotIn("相似度", sources)

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
        self.assertNotIn("stream failed", final_history[-1]["content"])

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




if __name__ == "__main__":
    unittest.main()
