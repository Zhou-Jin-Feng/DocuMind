import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from app import __version__
from app.config import Settings


class SettingsTests(unittest.TestCase):
    def test_application_version_matches_current_release(self):
        self.assertEqual(__version__, "2.0.0")

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
        self.assertEqual(Settings.model_fields["metrics_host"].default, "127.0.0.1")

    def test_readiness_probe_timeout_is_bounded(self):
        self.assertEqual(
            Settings.model_fields["readiness_probe_timeout_seconds"].default,
            2.0,
        )
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, readiness_probe_timeout_seconds=0)
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, readiness_probe_timeout_seconds=31)

    def test_log_formats_are_normalized_and_validated(self):
        config = Settings(
            _env_file=None,
            log_console_format=" TEXT ",
            log_file_format=" JSON ",
        )
        self.assertEqual(config.log_console_format, "text")
        self.assertEqual(config.log_file_format, "json")
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, log_file_format="xml")

    def test_tracing_is_disabled_and_endpoint_is_optional_by_default(self):
        config = Settings(_env_file=None)
        self.assertFalse(config.tracing_enabled)
        self.assertIsNone(config.otel_exporter_otlp_endpoint)

        configured = Settings(
            _env_file=None,
            tracing_enabled=True,
            otel_exporter_otlp_endpoint="  http://127.0.0.1:4318/v1/traces  ",
        )
        self.assertEqual(
            configured.otel_exporter_otlp_endpoint,
            "http://127.0.0.1:4318/v1/traces",
        )

    def test_milvus_connection_defaults_and_normalization(self):
        config = Settings(
            _env_file=None,
            milvus_uri="  http://milvus:19530  ",
            milvus_token="   ",
            milvus_db_name="  rag  ",
        )
        self.assertEqual(config.milvus_uri, "http://milvus:19530")
        self.assertIsNone(config.milvus_token)
        self.assertEqual(config.milvus_db_name, "rag")

        with self.assertRaises(ValidationError):
            Settings(_env_file=None, milvus_uri="   ")

    def test_empty_optional_value_in_env_template_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text("RETRIEVAL_SCORE_THRESHOLD=\n", encoding="utf-8")
            config = Settings(_env_file=env_path)
        self.assertIsNone(config.retrieval_score_threshold)


if __name__ == "__main__":
    unittest.main()
