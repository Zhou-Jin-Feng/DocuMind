import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from app.api.schemas import (
    RETRIEVAL_VERSION,
    RETRIEVE_SCHEMA_VERSION,
    ErrorResponse,
    RetrieveRequest,
    RetrieveResponse,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "docs" / "contracts" / "retrieve-v1.schema.json"


def request_payload(**overrides):
    payload = {
        "schema_version": RETRIEVE_SCHEMA_VERSION,
        "query": "  What evidence supports the claim?  ",
        "document_key": "a" * 64,
        "expected_index_id": "b" * 64,
        "top_k": 3,
        "retrieval_mode": "dense",
        "distance_threshold": None,
    }
    payload.update(overrides)
    return payload


def response_payload(**overrides):
    payload = {
        "schema_version": RETRIEVE_SCHEMA_VERSION,
        "service_version": "2.1.0",
        "retrieval_version": RETRIEVAL_VERSION,
        "retrieval_mode": "dense",
        "document_key": "a" * 64,
        "index_id": "b" * 64,
        "source_sha256": "c" * 64,
        "chunks": [
            {
                "chunk_id": "d" * 64,
                "content": "A retrieved evidence chunk.",
                "content_sha256": "e" * 64,
                "source": "paper.pdf",
                "page_number": 3,
                "distance": 0.42,
                "rank": 1,
            }
        ],
    }
    payload.update(overrides)
    return payload


class RetrieveContractTests(unittest.TestCase):
    def test_request_normalizes_query_and_accepts_frozen_contract(self):
        request = RetrieveRequest(**request_payload())

        self.assertEqual(request.query, "What evidence supports the claim?")
        self.assertEqual(request.retrieval_mode, "dense")

    def test_request_rejects_unknown_fields_and_unsupported_values(self):
        invalid_payloads = (
            request_payload(schema_version="2.0"),
            request_payload(retrieval_mode="hybrid"),
            request_payload(top_k=0),
            request_payload(top_k=21),
            request_payload(document_key="doc-1"),
            request_payload(distance_threshold=float("inf")),
            request_payload(unknown_field=True),
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                RetrieveRequest(**payload)

    def test_response_accepts_empty_or_ordered_whitelisted_chunks(self):
        response = RetrieveResponse(**response_payload())
        empty = RetrieveResponse(**response_payload(chunks=[]))

        self.assertEqual(response.chunks[0].rank, 1)
        self.assertEqual(empty.chunks, [])

    def test_checked_in_json_schema_matches_provider_models(self):
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

        self.assertEqual(contract["schema_version"], RETRIEVE_SCHEMA_VERSION)
        self.assertEqual(contract["request"], RetrieveRequest.model_json_schema())
        self.assertEqual(contract["response"], RetrieveResponse.model_json_schema())
        self.assertEqual(contract["error"], ErrorResponse.model_json_schema())


if __name__ == "__main__":
    unittest.main()
