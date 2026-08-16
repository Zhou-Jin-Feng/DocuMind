import unittest

from app.core.reranker import CrossEncoderReranker
from app.core.retriever import RetrievalResult


class FakeCrossEncoder:
    def __init__(self, model_name, **kwargs):
        self.model_name = model_name
        self.kwargs = kwargs
        self.calls = []

    def predict(self, pairs, **kwargs):
        self.calls.append((pairs, kwargs))
        return [0.1, 0.9, 0.9]


class CrossEncoderRerankerTests(unittest.TestCase):
    def test_model_is_lazy_and_rerank_preserves_retrieval_evidence(self):
        created = []

        def factory(*args, **kwargs):
            model = FakeCrossEncoder(*args, **kwargs)
            created.append(model)
            return model

        reranker = CrossEncoderReranker(
            "fake/model",
            batch_size=4,
            device="cpu",
            local_files_only=True,
            model_factory=factory,
        )
        self.assertFalse(reranker.is_loaded)
        self.assertEqual(reranker.rerank("q", [], top_k=2), [])
        self.assertFalse(reranker.is_loaded)

        candidates = [
            RetrievalResult("first", {"chunk_id": "a"}, 0.1, 1, fusion_score=0.8),
            RetrievalResult("second", {"chunk_id": "b"}, 0.2, 2, lexical_score=3.0),
            RetrievalResult("third", {"chunk_id": "c"}, 0.3, 3),
        ]
        results = reranker.rerank("q", candidates, top_k=2)

        self.assertTrue(reranker.is_loaded)
        self.assertEqual(
            [result.metadata["chunk_id"] for result in results], ["b", "c"]
        )
        self.assertEqual([result.rank for result in results], [1, 2])
        self.assertEqual(results[0].distance, 0.2)
        self.assertEqual(results[0].lexical_score, 3.0)
        self.assertEqual(candidates[1].rank, 2)
        self.assertIsNone(candidates[1].rerank_score)
        self.assertEqual(
            created[0].kwargs,
            {"device": "cpu", "local_files_only": True},
        )
        self.assertEqual(created[0].calls[0][1]["batch_size"], 4)

    def test_invalid_score_count_is_rejected(self):
        class BrokenModel:
            def predict(self, pairs, **kwargs):
                del pairs, kwargs
                return [0.5]

        reranker = CrossEncoderReranker(
            "fake/model",
            model_factory=lambda *args, **kwargs: BrokenModel(),
        )
        candidates = [
            RetrievalResult("a", {"chunk_id": "a"}, 0.1, 1),
            RetrievalResult("b", {"chunk_id": "b"}, 0.2, 2),
        ]
        with self.assertRaisesRegex(ValueError, "分数数量"):
            reranker.rerank("q", candidates, top_k=1)


if __name__ == "__main__":
    unittest.main()
