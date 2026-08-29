import unittest

from app.core.retriever import RetrievalResult
from app.services.retrieval_service import (
    DocumentIndexUnavailableError,
    DocumentNotFoundError,
    RetrievalScopeViolationError,
    RetrievalService,
    StaleDocumentIndexError,
)

DOCUMENT_KEY = "a" * 64
INDEX_ID = "b" * 64
SOURCE_SHA256 = "c" * 64


class FakeRegistry:
    def __init__(self, *, document=None, index=None):
        self.document = document
        self.index = index

    def get_document(self, document_key):
        return self.document if document_key == DOCUMENT_KEY else None

    def get_index(self, index_id):
        return self.index if index_id == INDEX_ID else None


class CapturingRetriever:
    def __init__(self, results=()):
        self.results = list(results)
        self.calls = []

    def retrieve_semantic(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return self.results


class MutatingRetriever(CapturingRetriever):
    def __init__(self, registry, results=()):
        super().__init__(results)
        self.registry = registry

    def retrieve_semantic(self, query, **kwargs):
        results = super().retrieve_semantic(query, **kwargs)
        self.registry.document["active_index_id"] = "f" * 64
        return results


def document(**overrides):
    value = {
        "document_key": DOCUMENT_KEY,
        "tenant_id": "default",
        "collection_id": "rag_documents",
        "active_index_id": INDEX_ID,
    }
    value.update(overrides)
    return value


def index(**overrides):
    value = {
        "index_id": INDEX_ID,
        "document_key": DOCUMENT_KEY,
        "tenant_id": "default",
        "collection_id": "rag_documents",
        "status": "active",
        "source_sha256": SOURCE_SHA256,
    }
    value.update(overrides)
    return value


def result(**metadata_overrides):
    metadata = {
        "tenant_id": "default",
        "collection_id": "rag_documents",
        "document_key": DOCUMENT_KEY,
        "index_id": INDEX_ID,
        "chunk_id": "d" * 64,
    }
    metadata.update(metadata_overrides)
    return RetrievalResult(
        content="Evidence",
        metadata=metadata,
        distance=0.2,
        rank=1,
    )


class RetrievalServiceTests(unittest.TestCase):
    def service(self, *, retriever=None, registry=None):
        return RetrievalService(
            retriever=retriever or CapturingRetriever(),
            registry=registry or FakeRegistry(document=document(), index=index()),
            tenant_id="default",
            collection_id="rag_documents",
        )

    def test_retrieve_uses_exact_document_index_scope(self):
        retriever = CapturingRetriever([result()])

        batch = self.service(retriever=retriever).retrieve(
            "  evidence query  ",
            document_key=DOCUMENT_KEY,
            expected_index_id=INDEX_ID,
            top_k=3,
            retrieval_mode="dense",
            distance_threshold=0.8,
        )

        self.assertEqual(batch.document_key, DOCUMENT_KEY)
        self.assertEqual(batch.index_id, INDEX_ID)
        self.assertEqual(batch.source_sha256, SOURCE_SHA256)
        self.assertEqual(batch.results[0].content, "Evidence")
        query, kwargs = retriever.calls[0]
        self.assertEqual(query, "evidence query")
        self.assertEqual(kwargs["top_k"], 3)
        self.assertEqual(kwargs["score_threshold"], 0.8)
        self.assertEqual(
            kwargs["metadata_filter"],
            {
                "tenant_id": "default",
                "collection_id": "rag_documents",
                "document_key": DOCUMENT_KEY,
                "index_id": INDEX_ID,
            },
        )
        self.assertTrue(kwargs["result_predicate"](result().metadata))
        self.assertFalse(
            kwargs["result_predicate"](result(document_key="other").metadata)
        )

    def test_retrieve_returns_empty_batch_without_generation_dependency(self):
        batch = self.service().retrieve(
            "no match",
            document_key=DOCUMENT_KEY,
            expected_index_id=INDEX_ID,
            top_k=3,
            retrieval_mode="dense",
        )

        self.assertEqual(batch.results, ())
        self.assertFalse(hasattr(self.service(), "rag_generator"))

    def test_retrieve_rejects_unknown_scope_and_unavailable_index(self):
        cases = (
            (
                FakeRegistry(document=None, index=None),
                INDEX_ID,
                DocumentNotFoundError,
            ),
            (
                FakeRegistry(document=document(active_index_id=None), index=None),
                INDEX_ID,
                DocumentIndexUnavailableError,
            ),
            (
                FakeRegistry(document=document(), index=index()),
                "e" * 64,
                StaleDocumentIndexError,
            ),
            (
                FakeRegistry(document=document(), index=index(status="indexing")),
                INDEX_ID,
                DocumentIndexUnavailableError,
            ),
        )

        for registry, expected_index_id, error_type in cases:
            with self.subTest(error_type=error_type), self.assertRaises(error_type):
                self.service(registry=registry).retrieve(
                    "query",
                    document_key=DOCUMENT_KEY,
                    expected_index_id=expected_index_id,
                    top_k=3,
                    retrieval_mode="dense",
                )

    def test_retrieve_fails_closed_on_out_of_scope_result(self):
        retriever = CapturingRetriever([result(document_key="other")])

        with self.assertRaises(RetrievalScopeViolationError):
            self.service(retriever=retriever).retrieve(
                "query",
                document_key=DOCUMENT_KEY,
                expected_index_id=INDEX_ID,
                top_k=3,
                retrieval_mode="dense",
            )

    def test_retrieve_rechecks_active_index_after_vector_search(self):
        registry = FakeRegistry(document=document(), index=index())
        retriever = MutatingRetriever(registry, [result()])

        with self.assertRaises(StaleDocumentIndexError):
            self.service(retriever=retriever, registry=registry).retrieve(
                "query",
                document_key=DOCUMENT_KEY,
                expected_index_id=INDEX_ID,
                top_k=3,
                retrieval_mode="dense",
            )


if __name__ == "__main__":
    unittest.main()
