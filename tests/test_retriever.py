import unittest

from app.core.retriever import RetrievalResult, Retriever


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


if __name__ == "__main__":
    unittest.main()
