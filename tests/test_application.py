import unittest
from unittest.mock import Mock, patch

from app.application import RAGApplication
from app.config import Settings


class ApplicationTests(unittest.TestCase):
    def test_failed_initialization_clears_partial_components(self):
        vector_store = Mock()
        application = RAGApplication(
            Settings(_env_file=None, metrics_enabled=False)
        )

        with (
            patch(
                "app.application.UniversalEmbeddingClient",
                return_value=object(),
            ),
            patch("app.application.VectorStore", return_value=vector_store),
            patch(
                "app.application.Retriever",
                side_effect=RuntimeError("retriever unavailable"),
            ),
        ):
            application.initialize()

        self.assertFalse(application.initialized)
        self.assertEqual(application.startup_error_type, "RuntimeError")
        self.assertIsNone(application.embedding_client)
        self.assertIsNone(application.vector_store)
        self.assertIsNone(application.retriever)
        self.assertIsNone(application.registry)
        self.assertEqual(
            application.readiness()["components"],
            {
                "application": "unavailable",
                "milvus": "unknown",
                "embedding": "unavailable",
                "llm": "unavailable",
                "registry": "unavailable",
            },
        )
        vector_store.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
