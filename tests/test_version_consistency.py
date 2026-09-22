import json
import re
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app import __version__
from app.api.main import create_app
from app.api.schemas import (
    RETRIEVAL_VERSION,
    RETRIEVE_SCHEMA_VERSION,
    RetrieveResponse,
)
from tests.test_api import FakeApplication

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "3.1.0"


class VersionConsistencyTests(unittest.TestCase):
    def test_application_and_frontend_versions_agree(self):
        package = json.loads(
            (ROOT / "frontend/package.json").read_text(encoding="utf-8")
        )
        lock = json.loads(
            (ROOT / "frontend/package-lock.json").read_text(encoding="utf-8")
        )
        self.assertEqual(__version__, EXPECTED_VERSION)
        self.assertEqual(package["version"], __version__)
        self.assertEqual(lock["version"], __version__)
        self.assertEqual(lock["packages"][""]["version"], __version__)
        mock_api = (ROOT / "frontend/e2e/mock-api.mjs").read_text(encoding="utf-8")
        match = re.search(r'version: "([^"]+)"', mock_api)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), __version__)

    def test_openapi_root_and_health_use_application_version(self):
        application = FakeApplication()
        with TestClient(create_app(application, configure_runtime=False)) as client:
            self.assertEqual(client.get("/").json()["version"], EXPECTED_VERSION)
            self.assertEqual(
                client.get("/api/v1/health/live").json()["version"], EXPECTED_VERSION
            )
            self.assertEqual(
                client.get("/api/v1/health/ready").json()["version"], EXPECTED_VERSION
            )
            self.assertEqual(
                client.get("/openapi.json").json()["info"]["version"], EXPECTED_VERSION
            )

    def test_current_examples_update_service_version_not_schema(self):
        schema = json.loads(
            (ROOT / "docs/contracts/retrieve-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        fixtures = json.loads(
            (ROOT / "docs/contracts/retrieve-v1.fixtures.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(RETRIEVE_SCHEMA_VERSION, "1.0")
        self.assertEqual(RETRIEVAL_VERSION, "dense-v1")
        self.assertEqual(schema["schema_version"], "1.0")
        self.assertEqual(fixtures["schema_version"], "1.0")
        self.assertEqual(schema["response"], RetrieveResponse.model_json_schema())
        for example in schema["response"]["examples"]:
            self.assertEqual(example["service_version"], EXPECTED_VERSION)
            self.assertEqual(example["schema_version"], "1.0")
            self.assertEqual(example["retrieval_version"], "dense-v1")
        self.assertEqual(
            fixtures["valid"]["response"]["service_version"], EXPECTED_VERSION
        )
        for case in fixtures["invalid"]["response"]:
            if "service_version" in case["payload"]:
                self.assertEqual(case["payload"]["service_version"], EXPECTED_VERSION)

    def test_retrieval_contract_accepts_old_and_new_application_versions(self):
        schema = json.loads(
            (ROOT / "docs/contracts/retrieve-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        fixtures = json.loads(
            (ROOT / "docs/contracts/retrieve-v1.fixtures.json").read_text(
                encoding="utf-8"
            )
        )
        for version in ["2.2.0", EXPECTED_VERSION]:
            with self.subTest(version=version):
                payload = dict(fixtures["valid"]["response"], service_version=version)
                Draft202012Validator(schema["response"]).validate(payload)
                parsed = RetrieveResponse(**payload)
                self.assertEqual(parsed.service_version, version)
                self.assertEqual(parsed.schema_version, "1.0")
                self.assertEqual(parsed.retrieval_version, "dense-v1")


if __name__ == "__main__":
    unittest.main()
