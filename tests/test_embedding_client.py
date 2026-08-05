import unittest

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


if __name__ == "__main__":
    unittest.main()
