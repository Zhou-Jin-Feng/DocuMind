import os
import unittest
import uuid

from langchain_core.documents import Document

from app.config import settings
from app.core.vector_store import VectorStore


@unittest.skipUnless(
    os.getenv("MILVUS_INTEGRATION_TEST") == "1",
    "Set MILVUS_INTEGRATION_TEST=1 to run against a real Milvus service",
)
class MilvusIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.store = VectorStore(
            collection_name=f"rag_integration_{uuid.uuid4().hex}",
            uri=os.getenv("MILVUS_TEST_URI", settings.milvus_uri),
            token=os.getenv("MILVUS_TEST_TOKEN") or settings.milvus_token,
            db_name=os.getenv("MILVUS_TEST_DB_NAME", settings.milvus_db_name),
        )
        self.store.ensure_embedding_space("integration", "fixed-v1", 3)

    def tearDown(self):
        self.store.delete_collection()
        self.store.close()

    def test_upsert_filtered_search_and_delete(self):
        documents = [
            Document(
                page_content="Milvus stores vector embeddings.",
                metadata={
                    "chunk_id": "chunk-a",
                    "document_id": "doc-a",
                    "index_id": "index-a",
                    "tenant_id": "default",
                },
            ),
            Document(
                page_content="RAG augments generation with retrieval.",
                metadata={
                    "chunk_id": "chunk-b",
                    "document_id": "doc-b",
                    "index_id": "index-b",
                    "tenant_id": "default",
                },
            ),
        ]
        self.store.add_documents(
            documents,
            [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        )

        results = self.store.search(
            [1.0, 0.0, 0.0],
            n_results=2,
            where={"index_id": "index-a"},
        )
        self.assertEqual(results["ids"], ["chunk-a"])
        self.assertEqual(results["distances"], [0.0])
        self.assertEqual(self.store.count(), 2)
        self.assertEqual(self.store.count_by_index_id("index-a"), 1)
        self.assertEqual(self.store.list_ids_by_index_id("index-a"), ["chunk-a"])
        self.assertEqual(
            self.store.index_inventory(),
            ({"index-a": 1, "index-b": 1}, 0),
        )
        self.assertEqual(self.store.list_index_ids(), ["index-a", "index-b"])
        self.assertEqual(
            self.store.get_collection_info()["metadata"],
            {
                "embedding_provider": "integration",
                "embedding_model": "fixed-v1",
                "embedding_dimension": 3,
            },
        )
        self.assertEqual(len(self.store.peek_documents(limit=1)["ids"]), 1)

        self.store.delete_by_index_id("index-a")
        self.assertEqual(self.store.count(), 1)
        self.store.delete_by_ids(["chunk-b"])
        self.assertEqual(self.store.count(), 0)


if __name__ == "__main__":
    unittest.main()
