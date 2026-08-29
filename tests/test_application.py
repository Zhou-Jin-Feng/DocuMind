import unittest
from unittest.mock import Mock, patch

from app.application import RAGApplication
from app.config import Settings


class ApplicationTests(unittest.TestCase):
    def _ready_application(self):
        application = RAGApplication(
            Settings(
                _env_file=None,
                metrics_enabled=False,
                readiness_probe_timeout_seconds=0.5,
            )
        )
        application.initialized = True
        application.embedding_client = Mock()
        application.embedding_client.health_check.return_value = True
        application.vector_store = Mock()
        application.vector_store.client.list_collections.return_value = []
        application.llm_client = Mock(
            provider="openai",
            model="gpt-test",
            client=Mock(),
        )
        application.registry = object()
        application.retrieval_service = object()
        return application

    def test_readiness_probes_milvus_and_embedding(self):
        application = self._ready_application()

        report = application.readiness()

        self.assertTrue(report["ready"])
        self.assertEqual(report["status"], "ready")
        application.vector_store.client.list_collections.assert_called_once_with(
            timeout=0.5
        )
        application.embedding_client.health_check.assert_called_once_with(
            timeout_seconds=0.5
        )

    def test_readiness_marks_unreachable_embedding_as_degraded(self):
        application = self._ready_application()
        application.embedding_client.health_check.side_effect = ConnectionError(
            "Ollama unavailable"
        )

        report = application.readiness()

        self.assertFalse(report["ready"])
        self.assertEqual(report["status"], "degraded")
        self.assertEqual(report["components"]["embedding"], "unavailable")
        self.assertEqual(report["error_type"], "dependency_unavailable")

    def test_readiness_marks_unreachable_milvus_as_degraded_without_retry(self):
        application = self._ready_application()
        application.vector_store.client.list_collections.side_effect = ConnectionError(
            "Milvus unavailable"
        )

        report = application.readiness()

        self.assertFalse(report["ready"])
        self.assertEqual(report["components"]["milvus"], "unavailable")
        self.assertEqual(report["error_type"], "dependency_unavailable")
        application.vector_store.client.list_collections.assert_called_once_with(
            timeout=0.5
        )

    def test_llm_readiness_does_not_call_generation_api(self):
        application = self._ready_application()
        llm_client = application.llm_client.client

        application.readiness()

        self.assertEqual(llm_client.mock_calls, [])

    def test_failed_initialization_clears_partial_components(self):
        vector_store = Mock()
        application = RAGApplication(Settings(_env_file=None, metrics_enabled=False))

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
                "retrieval": "unavailable",
            },
        )
        vector_store.close.assert_called_once_with()

    def test_initialization_wires_retrieval_execution_policy(self):
        config = Settings(
            _env_file=None,
            metrics_enabled=False,
            retrieval_connection_timeout_seconds=1.5,
            retrieval_embedding_timeout_seconds=8.0,
            retrieval_milvus_timeout_seconds=3.0,
            retrieval_max_concurrency=2,
            retrieval_queue_timeout_seconds=0.5,
            retrieval_max_attempts=3,
            retrieval_retry_backoff_seconds=0.2,
        )
        application = RAGApplication(config)
        embedding_client = Mock(provider="ollama", config={"model": "test"})
        vector_store = Mock()

        with (
            patch(
                "app.application.UniversalEmbeddingClient",
                return_value=embedding_client,
            ) as embedding_class,
            patch(
                "app.application.VectorStore",
                return_value=vector_store,
            ) as vector_store_class,
            patch("app.application.UniversalLLMClient", return_value=Mock()),
            patch("app.application.DocumentRegistry", return_value=Mock()),
        ):
            application.initialize()

        self.assertTrue(application.initialized)
        embedding_class.assert_called_once_with(
            config.default_embedding_provider,
            connection_timeout_seconds=1.5,
            request_timeout_seconds=8.0,
        )
        vector_store_class.assert_called_once_with(
            collection_name=config.collection_name,
            uri=config.milvus_uri,
            token=config.milvus_token,
            db_name=config.milvus_db_name,
            connection_timeout_seconds=1.5,
        )
        service = application.retrieval_service
        self.assertEqual(service.queue_timeout_seconds, 0.5)
        self.assertEqual(service.embedding_timeout_seconds, 8.0)
        self.assertEqual(service.vector_search_timeout_seconds, 3.0)
        self.assertEqual(service.max_attempts, 3)
        self.assertEqual(service.retry_backoff_seconds, 0.2)

    def test_llm_failure_keeps_pure_retrieval_ready(self):
        application = RAGApplication(Settings(_env_file=None, metrics_enabled=False))
        embedding_client = Mock(provider="ollama", config={"model": "test"})
        embedding_client.health_check.return_value = True
        vector_store = Mock()
        vector_store.client.list_collections.return_value = []

        with (
            patch(
                "app.application.UniversalEmbeddingClient",
                return_value=embedding_client,
            ),
            patch("app.application.VectorStore", return_value=vector_store),
            patch(
                "app.application.UniversalLLMClient",
                side_effect=RuntimeError("LLM unavailable"),
            ),
            patch("app.application.DocumentRegistry", return_value=Mock()),
        ):
            application.initialize()

        self.assertTrue(application.initialized)
        self.assertIsNone(application.startup_error_type)
        self.assertEqual(application.llm_startup_error_type, "RuntimeError")
        self.assertIsNotNone(application.retrieval_service)
        self.assertIsNotNone(application.document_service)
        self.assertIsNone(application.rag_service)
        readiness = application.readiness()
        self.assertFalse(readiness["ready"])
        self.assertEqual(readiness["components"]["retrieval"], "ready")
        self.assertEqual(readiness["components"]["llm"], "unavailable")


if __name__ == "__main__":
    unittest.main()
