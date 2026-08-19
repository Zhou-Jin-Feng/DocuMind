import unittest
from types import SimpleNamespace

from app.core.generator import GenerationConfig, RAGGenerator, UniversalLLMClient
from app.core.retriever import RetrievalResult


class FakeClaudeMessages:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(content=[SimpleNamespace(text="回答")])


class GeneratorTests(unittest.TestCase):
    def test_generation_config_validation(self):
        with self.assertRaises(ValueError):
            GenerationConfig(temperature=2.1)
        with self.assertRaises(ValueError):
            GenerationConfig(max_tokens=0)
        with self.assertRaises(ValueError):
            UniversalLLMClient(request_timeout_seconds=0)

    def test_claude_system_prompt_is_sent_separately(self):
        messages_api = FakeClaudeMessages()
        client = UniversalLLMClient.__new__(UniversalLLMClient)
        client.provider = "claude"
        client.model = "claude-test"
        client.client = SimpleNamespace(messages=messages_api)

        answer = client.generate(
            [
                {"role": "system", "content": "系统规则"},
                {"role": "user", "content": "问题"},
            ],
            GenerationConfig(stream=False),
        )
        self.assertEqual(answer, "回答")
        self.assertEqual(messages_api.kwargs["system"], "系统规则")
        self.assertEqual(
            messages_api.kwargs["messages"],
            [{"role": "user", "content": "问题"}],
        )

    def test_rag_generator_uses_one_based_page_number(self):
        generator = RAGGenerator.__new__(RAGGenerator)
        result = RetrievalResult(
            content="正文",
            metadata={"source_file": "manual.pdf", "page_number": 3},
            distance=0.2,
            rank=1,
        )
        context = generator._build_context_from_retrieval([result])
        self.assertIn("manual.pdf 第3页", context)

    def test_rag_generator_prompt_templates_preserve_current_format(self):
        generator = RAGGenerator.__new__(RAGGenerator)
        result = RetrievalResult(
            content="正文",
            metadata={"source_file": "manual.pdf", "page_number": 3},
            distance=0.2,
            rank=1,
        )

        context = generator._build_context_from_retrieval([result])
        messages = generator._build_prompt("问题", context)

        self.assertEqual(
            context,
            "以下是相关文档内容：\n\n[文档1] 来源: manual.pdf 第3页\n正文\n",
        )
        self.assertEqual(messages[0]["content"], RAGGenerator.SYSTEM_PROMPT)
        self.assertEqual(
            messages[1]["content"],
            f"{context}\n\n用户问题：问题\n\n请基于上述文档回答：",
        )

    def test_streaming_error_propagates(self):
        class BrokenLLM:
            def generate_stream(self, messages, config):
                yield "部分"
                raise RuntimeError("provider down")

        generator = RAGGenerator(BrokenLLM())
        stream = generator.generate_answer_stream("问题", [], GenerationConfig())
        self.assertEqual(next(stream), "部分")
        with self.assertRaises(RuntimeError):
            next(stream)


if __name__ == "__main__":
    unittest.main()
