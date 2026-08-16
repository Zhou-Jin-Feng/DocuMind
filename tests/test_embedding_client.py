import unittest

from io import BytesIO
from unittest.mock import Mock, patch

from app.config import settings
from app.core.embedding_client import UniversalEmbeddingClient


class EmbeddingClientTests(unittest.TestCase):
    def setUp(self):
        self.client = UniversalEmbeddingClient.__new__(UniversalEmbeddingClient)
        self.client.config = {"max_batch_size": 10}
        self.client.type = "api"

    def test_batch_rejects_empty_text_without_changing_alignment(self):
        with self.assertRaisesRegex(ValueError, "索引位置"):
            self.client.embed_texts_batch(["有效文本", "  "], show_progress=False)

    def test_batch_parameters_are_validated(self):
        with self.assertRaisesRegex(ValueError, "max_retries"):
            self.client.embed_texts_batch(["文本"], max_retries=0, show_progress=False)
        with self.assertRaisesRegex(ValueError, "batch_size"):
            self.client.embed_texts_batch(["文本"], batch_size=0, show_progress=False)

    def test_ollama_configuration_has_model_compatible_fallback_dimension(self):
        with patch.object(
            settings,
            "ollama_embedding_model",
            "qwen3-embedding",
        ), patch.object(settings, "ollama_embedding_dimensions", None):
            config = UniversalEmbeddingClient.configuration_for("ollama")

        self.assertEqual(config["model"], "qwen3-embedding")
        self.assertEqual(config["dimensions"], 4096)

    def test_ollama_configuration_accepts_explicit_dimension_override(self):
        with patch.object(settings, "ollama_embedding_dimensions", 768):
            config = UniversalEmbeddingClient.configuration_for("ollama")

        self.assertEqual(config["dimensions"], 768)

    def test_ollama_embedding_retries_transient_failures(self):
        self.client.type = "local"

        class FlakyOllama:
            def __init__(self):
                self.calls = 0

            def embed_query(self, text):
                self.calls += 1
                if self.calls < 3:
                    raise RuntimeError("temporary Ollama failure")
                return [1.0, 2.0]

        ollama = FlakyOllama()
        self.client.ollama_client = ollama
        with patch("app.core.embedding_client.time.sleep") as sleep:
            embedding = self.client.embed_text("文本")

        self.assertEqual(embedding, [1.0, 2.0])
        self.assertEqual(ollama.calls, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_api_health_check_only_checks_initialized_client(self):
        self.client.client = object()
        self.assertTrue(self.client.health_check(timeout_seconds=1))

        self.client.client = None
        self.assertFalse(self.client.health_check(timeout_seconds=1))

    def test_ollama_health_check_requires_service_and_configured_model(self):
        self.client.type = "local"
        self.client.base_url = "http://127.0.0.1:11434"
        self.client.config = {"model": "qwen3-embedding", "dimensions": 3}
        tags_response = BytesIO(
            b'{"models":[{"name":"qwen3-embedding:latest"}]}'
        )
        tags_response.status = 200
        tags_response.__enter__ = Mock(return_value=tags_response)
        tags_response.__exit__ = Mock(return_value=False)
        embed_response = BytesIO(b'{"embeddings":[[0.1,0.2,0.3]]}')
        embed_response.status = 200
        embed_response.__enter__ = Mock(return_value=embed_response)
        embed_response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.side_effect = [tags_response, embed_response]

        with patch("app.core.embedding_client.build_opener", return_value=opener):
            self.assertTrue(self.client.health_check(timeout_seconds=1.5))

        self.assertEqual(opener.open.call_count, 2)
        tags_request = opener.open.call_args_list[0].args[0]
        embed_request = opener.open.call_args_list[1].args[0]
        self.assertEqual(tags_request.full_url, "http://127.0.0.1:11434/api/tags")
        self.assertEqual(embed_request.full_url, "http://127.0.0.1:11434/api/embed")
        self.assertEqual(embed_request.method, "POST")
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 1.5)

    def test_ollama_health_check_rejects_missing_model(self):
        self.client.type = "local"
        self.client.base_url = "http://127.0.0.1:11434"
        self.client.config = {"model": "qwen3-embedding", "dimensions": 4096}
        response = BytesIO(b'{"models":[{"name":"nomic-embed-text:latest"}]}')
        response.status = 200
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = response

        with patch("app.core.embedding_client.build_opener", return_value=opener):
            with self.assertRaisesRegex(ConnectionError, "not installed"):
                self.client.health_check(timeout_seconds=1)

    def test_ollama_model_without_tag_only_matches_latest(self):
        self.assertTrue(
            self.client._ollama_model_available(
                "qwen3-embedding",
                ["qwen3-embedding:latest"],
            )
        )
        self.assertFalse(
            self.client._ollama_model_available(
                "qwen3-embedding",
                ["qwen3-embedding:experimental"],
            )
        )

    def test_ollama_health_check_uses_recent_success_cache(self):
        self.client.type = "local"
        self.client._ollama_health_expires_at = 100.0

        with patch("app.core.embedding_client.time.monotonic", return_value=99.0), patch(
            "app.core.embedding_client.build_opener"
        ) as build_opener:
            self.assertTrue(self.client.health_check(timeout_seconds=1))

        build_opener.assert_not_called()

    def test_ollama_health_check_propagates_timeout(self):
        self.client.type = "local"
        self.client.base_url = "http://127.0.0.1:11434"
        self.client.config = {"model": "qwen3-embedding", "dimensions": 3}
        opener = Mock()
        opener.open.side_effect = TimeoutError("timed out")

        with patch("app.core.embedding_client.build_opener", return_value=opener):
            with self.assertRaises(TimeoutError):
                self.client.health_check(timeout_seconds=1)

    def test_ollama_health_check_rejects_http_and_invalid_json(self):
        self.client.type = "local"
        self.client.base_url = "http://127.0.0.1:11434"
        self.client.config = {"model": "qwen3-embedding", "dimensions": 3}

        unavailable = BytesIO(b"{}")
        unavailable.status = 503
        unavailable.__enter__ = Mock(return_value=unavailable)
        unavailable.__exit__ = Mock(return_value=False)
        invalid_json = BytesIO(b"not-json")
        invalid_json.status = 200
        invalid_json.__enter__ = Mock(return_value=invalid_json)
        invalid_json.__exit__ = Mock(return_value=False)

        opener = Mock()
        with patch("app.core.embedding_client.build_opener", return_value=opener):
            opener.open.return_value = unavailable
            with self.assertRaisesRegex(ConnectionError, "HTTP 503"):
                self.client.health_check(timeout_seconds=1)

            opener.open.return_value = invalid_json
            with self.assertRaisesRegex(ConnectionError, "invalid JSON"):
                self.client.health_check(timeout_seconds=1)

    def test_ollama_health_check_rejects_embedding_dimension_mismatch(self):
        self.client.type = "local"
        self.client.base_url = "http://127.0.0.1:11434"
        self.client.config = {"model": "qwen3-embedding", "dimensions": 3}
        tags_response = BytesIO(
            b'{"models":[{"name":"qwen3-embedding:latest"}]}'
        )
        tags_response.status = 200
        tags_response.__enter__ = Mock(return_value=tags_response)
        tags_response.__exit__ = Mock(return_value=False)
        embed_response = BytesIO(b'{"embeddings":[[0.1,0.2]]}')
        embed_response.status = 200
        embed_response.__enter__ = Mock(return_value=embed_response)
        embed_response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.side_effect = [tags_response, embed_response]

        with patch("app.core.embedding_client.build_opener", return_value=opener):
            with self.assertRaisesRegex(ConnectionError, "dimension mismatch"):
                self.client.health_check(timeout_seconds=1)


if __name__ == "__main__":
    unittest.main()
