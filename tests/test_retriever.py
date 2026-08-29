import unittest

from langchain_core.documents import Document

from app.core.query_rewriter import MappingQueryRewriter
from app.core.retriever import (
    BM25Retriever,
    HybridRetriever,
    MultiQueryRetriever,
    RerankingRetriever,
    RetrievalResult,
    Retriever,
)


class FakeEmbeddingClient:
    provider = "fake"
    config = {"model": "fake-model"}

    def __init__(self):
        self.calls = []

    def embed_text(self, text, **kwargs):
        self.calls.append((text, kwargs))
        if text == "explode":
            raise RuntimeError("embedding unavailable")
        return [1.0, 0.0]


class FakeVectorStore:
    def __init__(self):
        self.last_n_results = None
        self.embedding_space = None
        self.search_options = None

    def ensure_embedding_space(self, provider, model, dimension):
        self.embedding_space = (provider, model, dimension)

    def search(self, query_embedding, n_results, where=None, **kwargs):
        self.last_n_results = n_results
        self.search_options = kwargs
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
        self.embedding_client = FakeEmbeddingClient()
        self.retriever = Retriever(self.store, self.embedding_client)

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

    def test_dependency_timeouts_are_forwarded(self):
        self.retriever.retrieve_semantic(
            "query",
            embedding_timeout_seconds=9.0,
            vector_search_timeout_seconds=4.0,
            embedding_max_attempts=1,
        )

        self.assertEqual(
            self.embedding_client.calls[-1][1],
            {"timeout_seconds": 9.0, "max_attempts": 1},
        )
        self.assertEqual(self.store.search_options, {"timeout_seconds": 4.0})

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
                    metadata={
                        "chunk_id": "active",
                        "document_id": "lifecycle",
                        "active": True,
                    },
                ),
                Document(
                    page_content="普通天气预报和气温说明",
                    metadata={
                        "chunk_id": "weather",
                        "document_id": "weather",
                        "active": True,
                    },
                ),
            ]
        )

        results = retriever.retrieve_lexical(
            "dry_run 校验什么哈希",
            top_k=2,
            result_predicate=lambda metadata: metadata.get("active") is True,
        )

        self.assertEqual(
            [result.metadata["chunk_id"] for result in results], ["active"]
        )
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
                Document(
                    page_content="shared RRF exact", metadata={"chunk_id": "shared"}
                ),
                Document(
                    page_content="lexical RRF exact", metadata={"chunk_id": "lexical"}
                ),
            ]
        )
        hybrid = HybridRetriever(Dense(), lexical, rrf_k=60)

        results = hybrid.retrieve_semantic("RRF exact", top_k=3)

        self.assertEqual(len({result.metadata["chunk_id"] for result in results}), 3)
        shared = next(
            result for result in results if result.metadata["chunk_id"] == "shared"
        )
        self.assertEqual(shared.dense_rank, 2)
        self.assertEqual(shared.lexical_rank, 1)
        self.assertIsNotNone(shared.distance)
        self.assertIsNotNone(shared.lexical_score)
        self.assertAlmostEqual(shared.fusion_score, 1 / 62 + 1 / 61)
        lexical_only = next(
            result for result in results if result.metadata["chunk_id"] == "lexical"
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
                Document(
                    page_content="lexical exact", metadata={"chunk_id": "lexical"}
                ),
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
        shared = next(
            result for result in results if result.metadata["chunk_id"] == "shared"
        )
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

    def test_multi_query_rrf_deduplicates_by_stable_chunk_id(self):
        original_results = [
            RetrievalResult("original only", {"chunk_id": "original"}, 0.1, 1),
            RetrievalResult("shared", {"chunk_id": "shared"}, 0.2, 2),
        ]
        rewritten_results = [
            RetrievalResult("shared", {"chunk_id": "shared"}, 0.3, 1),
            RetrievalResult("rewrite only", {"chunk_id": "rewrite"}, 0.4, 2),
        ]

        class BaseRetriever:
            def __init__(self):
                self.calls = []

            def retrieve_semantic(self, query, top_k, **kwargs):
                self.calls.append((query, top_k, kwargs))
                return original_results if query == "why rrf" else rewritten_results

        base = BaseRetriever()
        retriever = MultiQueryRetriever(
            base,
            MappingQueryRewriter({"why rrf": ["rank fusion"]}),
            rrf_k=10,
            candidate_multiplier=2,
        )

        results = retriever.retrieve_semantic("why rrf", top_k=2, score_threshold=1.0)

        self.assertEqual(
            [result.metadata["chunk_id"] for result in results],
            ["shared", "original"],
        )
        self.assertEqual(base.calls[0], ("why rrf", 4, {"score_threshold": 1.0}))
        self.assertEqual(base.calls[1], ("rank fusion", 4, {"score_threshold": 1.0}))
        self.assertAlmostEqual(results[0].query_fusion_score, 1 / 12 + 1 / 11)
        self.assertEqual(results[0].query_ranks, {"why rrf": 2, "rank fusion": 1})
        self.assertIsNone(original_results[1].query_fusion_score)

    def test_multi_query_requires_stable_chunk_id(self):
        class BaseRetriever:
            def retrieve_semantic(self, query, top_k, **kwargs):
                del query, top_k, kwargs
                return [RetrievalResult("missing id", {}, 0.1, 1)]

        retriever = MultiQueryRetriever(
            BaseRetriever(),
            MappingQueryRewriter({}),
        )
        with self.assertRaisesRegex(ValueError, "chunk_id"):
            retriever.retrieve_semantic("q", top_k=1)

        class NonStringChunkIdRetriever:
            def retrieve_semantic(self, query, top_k, **kwargs):
                del query, top_k, kwargs
                return [RetrievalResult("numeric id", {"chunk_id": 1}, 0.1, 1)]

        retriever = MultiQueryRetriever(
            NonStringChunkIdRetriever(),
            MappingQueryRewriter({}),
        )
        with self.assertRaisesRegex(ValueError, "chunk_id"):
            retriever.retrieve_semantic("q", top_k=1)

    def test_reranking_retriever_expands_candidates_before_reranking(self):
        class BaseRetriever:
            def __init__(self):
                self.top_k = None

            def retrieve_semantic(self, query, top_k, **kwargs):
                del query, kwargs
                self.top_k = top_k
                return [RetrievalResult("a", {"chunk_id": "a"}, 0.1, 1)]

        class Reranker:
            def __init__(self):
                self.calls = []

            def rerank(self, query, candidates, *, top_k):
                self.calls.append((query, candidates, top_k))
                return list(candidates[:top_k])

        base = BaseRetriever()
        reranker = Reranker()
        retriever = RerankingRetriever(base, reranker, candidate_multiplier=5)

        results = retriever.retrieve_semantic("q", top_k=3)

        self.assertEqual(base.top_k, 15)
        self.assertEqual(reranker.calls[0][2], 3)
        self.assertEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()
