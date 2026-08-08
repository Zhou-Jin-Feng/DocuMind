import unittest

from langchain_core.documents import Document

from app.core.retriever import BM25Retriever, HybridRetriever, RetrievalResult, Retriever


class FakeEmbeddingClient:
    provider = "fake"
    config = {"model": "fake-model"}

    def embed_text(self, text):
        if text == "explode":
            raise RuntimeError("embedding unavailable")
        return [1.0, 0.0]


class FakeVectorStore:
    def __init__(self):
        self.last_n_results = None
        self.embedding_space = None

    def ensure_embedding_space(self, provider, model, dimension):
        self.embedding_space = (provider, model, dimension)

    def search(self, query_embedding, n_results, where=None):
        self.last_n_results = n_results
        return {
            "documents": ["RAG检索增强生成", "天气信息"],
            "metadatas": [
                {"source_file": "rag.txt", "page_number": 2},
                {"source_file": "weather.txt"},
            ],
            "distances": [0.2, 1.5],
            "ids": ["a", "b"],
        }


class RetrieverTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeVectorStore()
        self.retriever = Retriever(self.store, FakeEmbeddingClient())

    def test_threshold_uses_maximum_distance(self):
        results = self.retriever.retrieve_semantic(
            "什么是RAG",
            top_k=4,
            score_threshold=0.5,
        )
        self.assertEqual(self.store.last_n_results, 4)
        self.assertEqual(
            self.store.embedding_space,
            ("fake", "fake-model", 2),
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].distance, 0.2)
        self.assertEqual(results[0].page_number, 2)
        with self.assertRaises(ValueError):
            self.retriever.retrieve_semantic("什么是RAG", score_threshold=float("nan"))

    def test_system_failure_is_not_converted_to_empty_results(self):
        with self.assertRaises(RuntimeError):
            self.retriever.retrieve_semantic("explode")

    def test_chinese_rerank_preserves_distance(self):
        results = [
            RetrievalResult(
                content="RAG系统通过检索增强生成答案",
                metadata={"source_file": "a.txt"},
                distance=0.4,
                rank=1,
            ),
            RetrievalResult(
                content="今天适合散步",
                metadata={"source_file": "b.txt"},
                distance=0.2,
                rank=2,
            ),
        ]
        reranked = Retriever.rerank_results(results, "RAG检索增强", top_k=2)
        distances = {result.source: result.distance for result in reranked}
        self.assertEqual(distances, {"a.txt": 0.4, "b.txt": 0.2})
        self.assertTrue(all(result.rerank_score is not None for result in reranked))
        self.assertEqual(reranked[0].source, "a.txt")

    def test_bm25_retrieves_chinese_and_identifier_terms(self):
        retriever = BM25Retriever(
            [
                Document(
                    page_content="生命周期 dry_run 会校验 SHA_256 source hash",
                    metadata={"chunk_id": "active", "document_id": "lifecycle", "active": True},
                ),
                Document(
                    page_content="普通天气预报和气温说明",
                    metadata={"chunk_id": "weather", "document_id": "weather", "active": True},
                ),
            ]
        )

        results = retriever.retrieve_lexical(
            "dry_run 校验什么哈希",
            top_k=2,
            result_predicate=lambda metadata: metadata.get("active") is True,
        )

        self.assertEqual([result.metadata["chunk_id"] for result in results], ["active"])
        self.assertIsNone(results[0].distance)
        self.assertGreaterEqual(results[0].lexical_score, 0)
        self.assertEqual(results[0].lexical_rank, 1)

    def test_bm25_applies_metadata_filter_and_predicate(self):
        retriever = BM25Retriever(
            [
                Document(
                    page_content="RRF 混合检索",
                    metadata={"chunk_id": "a", "tenant": "a", "active": False},
                ),
                Document(
                    page_content="RRF 融合排序",
                    metadata={"chunk_id": "b", "tenant": "b", "active": True},
                ),
            ]
        )

        self.assertEqual(
            retriever.retrieve_lexical(
                "RRF",
                metadata_filter={"tenant": "a"},
                result_predicate=lambda metadata: metadata["active"],
            ),
            [],
        )

    def test_hybrid_rrf_deduplicates_and_preserves_channel_scores(self):
        dense_results = [
            RetrievalResult("dense only", {"chunk_id": "dense"}, 0.1, 1),
            RetrievalResult("shared", {"chunk_id": "shared"}, 0.2, 2),
        ]

        class Dense:
            def retrieve_semantic(self, *args, **kwargs):
                return dense_results

        lexical = BM25Retriever(
            [
                Document(page_content="shared RRF exact", metadata={"chunk_id": "shared"}),
                Document(page_content="lexical RRF exact", metadata={"chunk_id": "lexical"}),
            ]
        )
        hybrid = HybridRetriever(Dense(), lexical, rrf_k=60)

        results = hybrid.retrieve_semantic("RRF exact", top_k=3)

        self.assertEqual(len({result.metadata["chunk_id"] for result in results}), 3)
        shared = next(result for result in results if result.metadata["chunk_id"] == "shared")
        self.assertEqual(shared.dense_rank, 2)
        self.assertEqual(shared.lexical_rank, 1)
        self.assertIsNotNone(shared.distance)
        self.assertIsNotNone(shared.lexical_score)
        self.assertAlmostEqual(shared.fusion_score, 1 / 62 + 1 / 61)
        lexical_only = next(
            result
            for result in results
            if result.metadata["chunk_id"] == "lexical"
        )
        self.assertIsNone(lexical_only.distance)

    def test_hybrid_supports_weights_and_candidate_multiplier(self):
        dense_results = [
            RetrievalResult("shared", {"chunk_id": "shared"}, 0.1, 1),
            RetrievalResult("dense", {"chunk_id": "dense"}, 0.2, 2),
        ]

        class Dense:
            def __init__(self):
                self.calls = []

            def retrieve_semantic(self, *args, **kwargs):
                self.calls.append((args, kwargs))
                return dense_results

        dense = Dense()
        lexical = BM25Retriever(
            [
                Document(page_content="shared exact", metadata={"chunk_id": "shared"}),
                Document(page_content="lexical exact", metadata={"chunk_id": "lexical"}),
            ]
        )
        hybrid = HybridRetriever(
            dense,
            lexical,
            rrf_k=10,
            dense_weight=2.0,
            lexical_weight=3.0,
            candidate_multiplier=4,
        )

        results = hybrid.retrieve_hybrid("exact", top_k=2)

        self.assertEqual(dense.calls[0][1]["top_k"], 8)
        shared = next(result for result in results if result.metadata["chunk_id"] == "shared")
        self.assertAlmostEqual(shared.fusion_score, 2 / 11 + 3 / 11)

    def test_bm25_lexical_score_threshold_filters_low_score_hits(self):
        retriever = BM25Retriever(
            [
                Document(page_content="alpha beta", metadata={"chunk_id": "alpha"}),
                Document(page_content="gamma", metadata={"chunk_id": "gamma"}),
            ]
        )

        results = retriever.retrieve_lexical(
            "alpha",
            top_k=2,
            lexical_score_threshold=10**9,
        )

        self.assertEqual(results, [])
        with self.assertRaises(ValueError):
            retriever.retrieve_lexical("alpha", lexical_score_threshold=-0.1)

    def test_hybrid_rejects_invalid_calibration(self):
        lexical = BM25Retriever(
            [Document(page_content="alpha", metadata={"chunk_id": "alpha"})]
        )

        class Dense:
            def retrieve_semantic(self, *args, **kwargs):
                return []

        with self.assertRaises(ValueError):
            HybridRetriever(Dense(), lexical, dense_weight=0, lexical_weight=0)
        with self.assertRaises(ValueError):
            HybridRetriever(Dense(), lexical, candidate_multiplier=0)

    def test_hybrid_skips_zero_weight_channel(self):
        class DisabledDense:
            def retrieve_semantic(self, *args, **kwargs):
                raise AssertionError("zero-weight Dense channel should not run")

        lexical = BM25Retriever(
            [Document(page_content="RRF exact", metadata={"chunk_id": "lexical"})]
        )
        hybrid = HybridRetriever(
            DisabledDense(),
            lexical,
            dense_weight=0,
            lexical_weight=1,
        )

        results = hybrid.retrieve_hybrid("RRF exact", top_k=1)

        self.assertEqual(results[0].metadata["chunk_id"], "lexical")


if __name__ == "__main__":
    unittest.main()
