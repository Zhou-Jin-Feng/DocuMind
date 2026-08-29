import unittest
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from threading import Event

from app.core.retriever import RetrievalResult
from app.services.retrieval_service import (
    DocumentIndexUnavailableError,
    DocumentNotFoundError,
    DocumentOperationInProgressError,
    InvalidRetrievalEvidenceError,
    RetrievalBusyError,
    RetrievalDependencyTimeoutError,
    RetrievalScopeViolationError,
    RetrievalService,
    StaleDocumentIndexError,
)

DOCUMENT_KEY = "a" * 64
INDEX_ID = "b" * 64
SOURCE_SHA256 = "c" * 64


class FakeRegistry:
    def __init__(self, *, document=None, index=None, indexes=None):
        self.document = document
        self.index = index
        self.indexes = list(indexes or ([] if index is None else [index]))

    def get_document(self, document_key):
        return self.document if document_key == DOCUMENT_KEY else None

    def get_index(self, index_id):
        return self.index if index_id == INDEX_ID else None

    def list_indexes(self, **kwargs):
        del kwargs
        return tuple(self.indexes)


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


class FlakyRetriever(CapturingRetriever):
    def __init__(self, error, *, failures=1, results=()):
        super().__init__(results)
        self.error = error
        self.failures = failures

    def retrieve_semantic(self, query, **kwargs):
        self.calls.append((query, kwargs))
        if len(self.calls) <= self.failures:
            raise self.error
        return self.results


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


def result(content="Evidence", **metadata_overrides):
    metadata = {
        "tenant_id": "default",
        "collection_id": "rag_documents",
        "document_key": DOCUMENT_KEY,
        "index_id": INDEX_ID,
        "chunk_id": "d" * 64,
        "source_file": r"C:\private\paper.pdf",
        "page_number": 4,
    }
    metadata.update(metadata_overrides)
    return RetrievalResult(
        content=content,
        metadata=metadata,
        distance=0.2,
        rank=1,
    )


class RetrievalServiceTests(unittest.TestCase):
    def service(self, *, retriever=None, registry=None, **policy):
        return RetrievalService(
            retriever=retriever or CapturingRetriever(),
            registry=registry or FakeRegistry(document=document(), index=index()),
            tenant_id="default",
            collection_id="rag_documents",
            **policy,
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
        self.assertEqual(batch.chunks[0].content, "Evidence")
        self.assertEqual(
            batch.chunks[0].content_sha256,
            sha256(b"Evidence").hexdigest(),
        )
        self.assertEqual(batch.chunks[0].source, "paper.pdf")
        self.assertEqual(batch.chunks[0].page_number, 4)
        query, kwargs = retriever.calls[0]
        self.assertEqual(query, "evidence query")
        self.assertEqual(kwargs["top_k"], 3)
        self.assertEqual(kwargs["score_threshold"], 0.8)
        self.assertEqual(kwargs["embedding_timeout_seconds"], 15.0)
        self.assertEqual(kwargs["vector_search_timeout_seconds"], 5.0)
        self.assertEqual(kwargs["embedding_max_attempts"], 1)
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

        self.assertEqual(batch.chunks, ())
        self.assertFalse(hasattr(self.service(), "rag_generator"))

    def test_retrieve_rejects_unknown_scope_and_unavailable_index(self):
        cases = (
            (
                FakeRegistry(document=None, index=None),
                INDEX_ID,
                DocumentNotFoundError,
            ),
            (
                FakeRegistry(
                    document=document(tenant_id="another-tenant"),
                    index=index(tenant_id="another-tenant"),
                ),
                INDEX_ID,
                DocumentNotFoundError,
            ),
            (
                FakeRegistry(
                    document=document(collection_id="another-collection"),
                    index=index(collection_id="another-collection"),
                ),
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
                DocumentOperationInProgressError,
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

    def test_retrieve_distinguishes_transitional_and_unavailable_index_states(self):
        cases = (
            ("pending", DocumentOperationInProgressError),
            ("indexing", DocumentOperationInProgressError),
            ("deleting", DocumentOperationInProgressError),
            ("failed", DocumentIndexUnavailableError),
            ("deleted", DocumentIndexUnavailableError),
        )

        for status, error_type in cases:
            registry = FakeRegistry(
                document=document(active_index_id=None),
                index=None,
                indexes=[index(status=status)],
            )
            with self.subTest(status=status), self.assertRaises(error_type):
                self.service(registry=registry).retrieve(
                    "query",
                    document_key=DOCUMENT_KEY,
                    expected_index_id=INDEX_ID,
                    top_k=3,
                    retrieval_mode="dense",
                )

    def test_retrieve_filters_cross_document_and_superseded_index_candidates(self):
        candidates = [
            result(),
            result(document_key="f" * 64, chunk_id="1" * 64),
            result(index_id="e" * 64, chunk_id="2" * 64),
        ]

        class FilteringRetriever(CapturingRetriever):
            def retrieve_semantic(self, query, **kwargs):
                self.calls.append((query, kwargs))
                predicate = kwargs["result_predicate"]
                return [item for item in self.results if predicate(item.metadata)]

        batch = self.service(retriever=FilteringRetriever(candidates)).retrieve(
            "query",
            document_key=DOCUMENT_KEY,
            expected_index_id=INDEX_ID,
            top_k=3,
            retrieval_mode="dense",
        )

        self.assertEqual([chunk.chunk_id for chunk in batch.chunks], ["d" * 64])

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

    def test_retrieve_retries_only_transient_failures_with_same_scope(self):
        retriever = FlakyRetriever(
            ConnectionError("temporary connection failure"),
            results=[result()],
        )
        waits = []
        service = self.service(
            retriever=retriever,
            max_attempts=2,
            retry_backoff_seconds=0.25,
            sleep=waits.append,
        )

        batch = service.retrieve(
            "query",
            document_key=DOCUMENT_KEY,
            expected_index_id=INDEX_ID,
            top_k=3,
            retrieval_mode="dense",
        )

        self.assertEqual(batch.chunks[0].chunk_id, "d" * 64)
        self.assertEqual(len(retriever.calls), 2)
        self.assertEqual(waits, [0.25])
        first_scope = retriever.calls[0][1]["metadata_filter"]
        second_scope = retriever.calls[1][1]["metadata_filter"]
        self.assertEqual(first_scope, second_scope)
        self.assertEqual(first_scope["document_key"], DOCUMENT_KEY)
        self.assertEqual(first_scope["index_id"], INDEX_ID)

    def test_retrieve_does_not_retry_non_transient_or_changed_index(self):
        validation_failure = FlakyRetriever(ValueError("invalid vector"))
        with self.assertRaises(ValueError):
            self.service(
                retriever=validation_failure,
                max_attempts=3,
                sleep=lambda _: None,
            ).retrieve(
                "query",
                document_key=DOCUMENT_KEY,
                expected_index_id=INDEX_ID,
                top_k=3,
                retrieval_mode="dense",
            )
        self.assertEqual(len(validation_failure.calls), 1)

        registry = FakeRegistry(document=document(), index=index())

        class MutatingFailureRetriever(CapturingRetriever):
            def retrieve_semantic(self, query, **kwargs):
                self.calls.append((query, kwargs))
                registry.document["active_index_id"] = "f" * 64
                raise ConnectionError("temporary failure")

        changed_index = MutatingFailureRetriever()
        with self.assertRaises(StaleDocumentIndexError):
            self.service(
                retriever=changed_index,
                registry=registry,
                max_attempts=2,
                sleep=lambda _: None,
            ).retrieve(
                "query",
                document_key=DOCUMENT_KEY,
                expected_index_id=INDEX_ID,
                top_k=3,
                retrieval_mode="dense",
            )
        self.assertEqual(len(changed_index.calls), 1)

    def test_retrieve_wraps_exhausted_timeout_and_releases_capacity(self):
        retriever = FlakyRetriever(TimeoutError("dependency timed out"), failures=10)
        service = self.service(
            retriever=retriever,
            max_concurrency=1,
            max_attempts=2,
            retry_backoff_seconds=0,
            sleep=lambda _: None,
        )

        for _ in range(2):
            with self.assertRaises(RetrievalDependencyTimeoutError):
                service.retrieve(
                    "query",
                    document_key=DOCUMENT_KEY,
                    expected_index_id=INDEX_ID,
                    top_k=3,
                    retrieval_mode="dense",
                )
        self.assertEqual(len(retriever.calls), 4)

    def test_retrieve_bounds_concurrency_until_dependency_call_exits(self):
        started = Event()
        release = Event()

        class BlockingRetriever(CapturingRetriever):
            def retrieve_semantic(self, query, **kwargs):
                self.calls.append((query, kwargs))
                started.set()
                if not release.wait(timeout=2):
                    raise TimeoutError("test release timed out")
                return [result()]

        retriever = BlockingRetriever()
        service = self.service(
            retriever=retriever,
            max_concurrency=1,
            queue_timeout_seconds=0.02,
            max_attempts=1,
        )
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                service.retrieve,
                "first",
                document_key=DOCUMENT_KEY,
                expected_index_id=INDEX_ID,
                top_k=3,
                retrieval_mode="dense",
            )
            self.assertTrue(started.wait(timeout=1))
            try:
                with self.assertRaises(RetrievalBusyError):
                    service.retrieve(
                        "second",
                        document_key=DOCUMENT_KEY,
                        expected_index_id=INDEX_ID,
                        top_k=3,
                        retrieval_mode="dense",
                    )
            finally:
                release.set()
            self.assertEqual(future.result(timeout=1).chunks[0].chunk_id, "d" * 64)

        self.assertEqual(
            service.retrieve(
                "third",
                document_key=DOCUMENT_KEY,
                expected_index_id=INDEX_ID,
                top_k=3,
                retrieval_mode="dense",
            )
            .chunks[0]
            .chunk_id,
            "d" * 64,
        )

    def test_retrieve_rejects_missing_stable_evidence_fields(self):
        invalid_results = (
            result(chunk_id=None),
            result(source_file=""),
            RetrievalResult(
                content="Evidence",
                metadata={
                    **result().metadata,
                    "chunk_id": "d" * 64,
                },
                distance=None,
                rank=1,
            ),
        )

        for invalid_result in invalid_results:
            with (
                self.subTest(result=invalid_result),
                self.assertRaises(InvalidRetrievalEvidenceError),
            ):
                self.service(retriever=CapturingRetriever([invalid_result])).retrieve(
                    "query",
                    document_key=DOCUMENT_KEY,
                    expected_index_id=INDEX_ID,
                    top_k=3,
                    retrieval_mode="dense",
                )

    def test_retrieve_preserves_full_content_and_exposes_only_whitelisted_fields(self):
        content = "Full evidence paragraph. " * 30

        batch = self.service(retriever=CapturingRetriever([result(content)])).retrieve(
            "query",
            document_key=DOCUMENT_KEY,
            expected_index_id=INDEX_ID,
            top_k=3,
            retrieval_mode="dense",
        )

        self.assertGreater(len(content), 240)
        self.assertEqual(batch.chunks[0].content, content)
        self.assertEqual(
            batch.chunks[0].content_sha256, sha256(content.encode()).hexdigest()
        )
        self.assertEqual(
            set(batch.to_dict()["chunks"][0]),
            {
                "chunk_id",
                "content",
                "content_sha256",
                "source",
                "page_number",
                "distance",
                "rank",
            },
        )


if __name__ == "__main__":
    unittest.main()
