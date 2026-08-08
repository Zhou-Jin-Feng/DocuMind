import unittest

from app.core.query_rewriter import (
    LLMQueryRewriter,
    MappingQueryRewriter,
    QueryRewriteResult,
)


class FakeLLMClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate(self, messages, config):
        self.calls.append((messages, config))
        return self.response


class QueryRewriterTests(unittest.TestCase):
    def test_result_preserves_original_normalizes_and_deduplicates(self):
        result = QueryRewriteResult.from_candidates(
            "  RRF   如何融合？ ",
            ["rrf 如何融合？", " 排名 融合 ", "排名 融合", "倒数排名融合"],
            max_rewrites=2,
        )

        self.assertEqual(
            result.queries,
            ("RRF 如何融合？", "排名 融合", "倒数排名融合"),
        )

    def test_mapping_rewriter_is_deterministic_and_falls_back_to_original(self):
        rewriter = MappingQueryRewriter({"q": ["q2", "q3"]}, max_rewrites=1)

        self.assertEqual(rewriter.rewrite(" q ").queries, ("q", "q2"))
        self.assertEqual(rewriter.rewrite("missing").queries, ("missing",))

    def test_llm_rewriter_uses_strict_json_and_zero_temperature(self):
        client = FakeLLMClient('{"queries":["向量和关键词如何融合", "RRF 排名融合"]}')
        rewriter = LLMQueryRewriter(client, max_rewrites=2)

        result = rewriter.rewrite("混合检索怎么合并结果？")

        self.assertEqual(result.queries[0], "混合检索怎么合并结果？")
        self.assertEqual(len(result.queries), 3)
        self.assertEqual(client.calls[0][1].temperature, 0.0)
        self.assertFalse(client.calls[0][1].stream)

    def test_llm_rewriter_rejects_markdown_extra_keys_and_non_strings(self):
        invalid_responses = (
            '```json\n{"queries":["q"]}\n```',
            '{"queries":["q"],"reason":"x"}',
            '{"queries":[1]}',
            '{"queries":[]}',
            '{"queries":["  "]}',
            '{"queries":["q", " q "]}',
            '{"queries":["q"]}',
            '{"queries":["q1", "q2", "q3"]}',
            '{"queries":["q2"],"queries":["q3"]}',
        )
        for response in invalid_responses:
            with self.subTest(response=response), self.assertRaises(ValueError):
                LLMQueryRewriter(FakeLLMClient(response)).rewrite("q")


if __name__ == "__main__":
    unittest.main()
