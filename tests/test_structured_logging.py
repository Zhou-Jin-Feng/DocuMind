import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from app.core.document_loader import UniversalDocumentLoader
from app.observability.context import request_context
from app.observability.logging import get_logger, reset_logger, setup_logger


class StructuredLoggingTests(unittest.TestCase):
    def tearDown(self):
        reset_logger()

    def test_import_does_not_create_log_directory(self):
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            os.chdir(directory)
            try:
                __import__("app.observability.logging")
                self.assertFalse((Path(directory) / "logs").exists())
            finally:
                os.chdir(original_cwd)

    def test_repeated_setup_does_not_duplicate_output(self):
        console = io.StringIO()
        setup_logger(log_file_path=None, console_sink=console)
        setup_logger(log_file_path=None, console_sink=console)
        console.seek(0)
        console.truncate(0)

        get_logger(__name__).info("only once", event="test_event")
        self.assertEqual(console.getvalue().count("only once"), 1)

    def test_json_log_has_standard_fields_and_request_context(self):
        console = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "nested" / "rag.jsonl"
            setup_logger(
                log_file_path=log_path,
                console_sink=console,
                service="rag-test",
                environment="test",
            )
            with request_context(request_id="req-123", trace_id="trace-123"):
                get_logger(__name__).info(
                    "retrieval done",
                    event="retrieval_completed",
                    operation="vector.search",
                    duration_ms=12.5,
                    status="success",
                )
            reset_logger()

            records = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
            ]
            record = next(
                item for item in records if item["event"] == "retrieval_completed"
            )
            self.assertEqual(record["service"], "rag-test")
            self.assertEqual(record["environment"], "test")
            self.assertEqual(record["request_id"], "req-123")
            self.assertEqual(record["trace_id"], "trace-123")
            self.assertEqual(record["operation"], "vector.search")
            self.assertEqual(record["duration_ms"], 12.5)
            self.assertEqual(record["status"], "success")
            self.assertIn("error_type", record)

    def test_exception_traceback_remains_valid_json(self):
        console = io.StringIO()
        setup_logger(
            log_file_path=None,
            console_sink=console,
            console_format="json",
        )
        try:
            raise RuntimeError("failed <stream>")
        except RuntimeError:
            get_logger(__name__).exception(
                "stream failed",
                event="response_sent",
                status="error",
            )

        records = [
            json.loads(line) for line in console.getvalue().splitlines() if line.strip()
        ]
        record = next(item for item in records if item["event"] == "response_sent")
        self.assertIn("failed <stream>", record["exception"])
        self.assertNotIn("_serialized_json", record.get("fields", {}))

    def test_document_loader_does_not_log_filename_or_content(self):
        console = io.StringIO()
        filename = "private-customer-contract.txt"
        content = "confidential-document-body-marker"
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            document_path = directory_path / filename
            log_path = directory_path / "rag.jsonl"
            document_path.write_text(content, encoding="utf-8")
            setup_logger(log_file_path=log_path, console_sink=console)
            try:
                documents = UniversalDocumentLoader().load_document(str(document_path))
            finally:
                reset_logger()

            log_content = log_path.read_text(encoding="utf-8")

        self.assertEqual(documents[0].metadata["source_file"], filename)
        self.assertNotIn(filename, log_content)
        self.assertNotIn(content, log_content)
        records = [json.loads(line) for line in log_content.splitlines()]
        loader_records = [
            record
            for record in records
            if record["module"] == "app.core.document_loader"
        ]
        self.assertEqual(
            [record["message"] for record in loader_records],
            ["正在加载文档", "文档加载完成"],
        )
        self.assertTrue(
            all(
                record.get("fields", {}).get("file_extension") == ".txt"
                for record in loader_records
            )
        )

    def test_secrets_are_redacted_from_message_and_fields(self):
        console = io.StringIO()
        secret = "sk-super-secret-value"
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "rag.jsonl"
            setup_logger(log_file_path=log_path, console_sink=console)
            get_logger(__name__).error(
                f"provider failed api_key={secret}",
                event="provider_failed",
                api_key=secret,
                nested={"authorization": f"Bearer {secret}"},
            )
            reset_logger()
            content = log_path.read_text(encoding="utf-8")

        self.assertNotIn(secret, content)
        self.assertIn("[REDACTED]", content)


if __name__ == "__main__":
    unittest.main()
