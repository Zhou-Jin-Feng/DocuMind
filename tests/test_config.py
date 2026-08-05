import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from app.config import Settings


class SettingsTests(unittest.TestCase):
    def test_chunk_overlap_must_be_smaller_than_chunk_size(self):
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, chunk_size=100, chunk_overlap=100)

    def test_extensions_and_providers_are_normalized(self):
        config = Settings(
            _env_file=None,
            default_embedding_provider=" OLLAMA ",
            default_llm_provider=" OpenAI ",
            allowed_extensions=["PDF", ".pdf", " Txt "],
        )
        self.assertEqual(config.default_embedding_provider, "ollama")
        self.assertEqual(config.default_llm_provider, "openai")
        self.assertEqual(config.allowed_extensions, [".pdf", ".txt"])

    def test_default_host_is_localhost(self):
        self.assertEqual(Settings.model_fields["server_host"].default, "127.0.0.1")

    def test_empty_optional_value_in_env_template_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text("RETRIEVAL_SCORE_THRESHOLD=\n", encoding="utf-8")
            config = Settings(_env_file=env_path)
        self.assertIsNone(config.retrieval_score_threshold)

if __name__ == "__main__":
    unittest.main()
