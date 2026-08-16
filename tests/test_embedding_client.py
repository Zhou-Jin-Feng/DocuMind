import unittest

from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
