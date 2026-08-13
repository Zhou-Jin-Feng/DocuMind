import unittest
from unittest.mock import patch

from langchain_core.documents import Document

from app.core.vector_store import VectorStore
from tests.fake_vector_store import FakeMilvusClient


class VectorStoreTests(unittest.TestCase):
    def setUp(self):
        self.client_patcher = patch(
            "app.core.vector_store.MilvusClient",
            FakeMilvusClient,
        )
        self.client_patcher.start()
        self.store = VectorStore(
            collection_name="unit_test_documents",
            uri="http://milvus.test:19530",
            db_name="unit_test",
        )

    def tearDown(self):
        self.store.close()
        self.store = None
        self.client_patcher.stop()

    @staticmethod
    def _documents():
        return [
            Document(
                page_content="RAG 使用检索结果增强生成。",
                metadata={
                    "document_id": "doc-1",
                    "chunk_id": "chunk-1",
                    "chunk_index": 0,
                    "source_file": "a.txt",
                },
            ),
            Document(
                page_content="向量数据库负责保存文档向量。",
                metadata={
                    "document_id": "doc-1",
                    "chunk_id": "chunk-2",
                    "chunk_index": 1,
                    "source_file": "a.txt",
                },
            ),
        ]

    def test_upsert_is_idempotent_and_document_can_be_deleted(self):
        documents = self._documents()
        embeddings = [[1.0, 0.0], [0.0, 1.0]]
        self.store.ensure_embedding_space("fake", "model-a", 2)
        self.store.add_documents(documents, embeddings)
        self.store.add_documents(documents, embeddings)
        self.assertEqual(self.store.count(), 2)

        results = self.store.search([1.0, 0.0], n_results=10)
        self.assertEqual(len(results["documents"]), 2)
        self.assertEqual(len(results["distances"]), 2)

        self.store.delete_by_document_id("doc-1")
        self.assertEqual(self.store.count(), 0)
        self.assertEqual(
            self.store.search([1.0, 0.0]),
            {"ids": [], "documents": [], "metadatas": [], "distances": []},
        )

    def test_embedding_count_and_dimensions_are_validated(self):
        documents = self._documents()
        self.store.ensure_embedding_space("fake", "model-a", 2)
        with self.assertRaises(ValueError):
            self.store.add_documents(documents, [[1.0, 0.0]])
        with self.assertRaisesRegex(ValueError, "dimensions"):
            self.store.add_documents(documents, [[1.0], [1.0, 0.0]])
        with self.assertRaisesRegex(ValueError, "Milvus Collection"):
            self.store.add_documents(documents, [[1.0] for _ in documents])
        with self.assertRaisesRegex(ValueError, "Query embedding dimension"):
            self.store.add_documents(documents, [[1.0, 0.0], [0.0, 1.0]])
            self.store.search([1.0, 0.0, 0.0])

    def test_milvus_varchar_limits_and_reserved_id_are_validated(self):
        self.store.ensure_embedding_space("fake", "model-a", 2)
        document = self._documents()[0]

        with self.assertRaisesRegex(ValueError, "reserved"):
            self.store.add_documents(
                [document],
                [[1.0, 0.0]],
                ids=[self.store._CONFIG_ID],
            )
        with self.assertRaisesRegex(ValueError, "Chunk ID exceeds"):
            self.store.add_documents(
                [document],
                [[1.0, 0.0]],
                ids=["界" * 171],
            )
        with self.assertRaisesRegex(ValueError, "Document chunk exceeds"):
            self.store.add_documents(
                [Document(page_content="界" * 21846)],
                [[1.0, 0.0]],
                ids=["large-document"],
            )

    def test_internal_config_record_cannot_be_deleted(self):
        self.store.ensure_embedding_space("fake", "model-a", 2)

        for reserved_id in (self.store._CONFIG_ID, f" {self.store._CONFIG_ID} "):
            with self.subTest(reserved_id=reserved_id):
                with self.assertRaisesRegex(ValueError, "reserved"):
                    self.store.delete_by_ids([reserved_id])

        self.assertIsNotNone(self.store._config_record())

    def test_empty_collection_still_validates_query_dimension(self):
        self.store.ensure_embedding_space("fake", "model-a", 2)

        with self.assertRaisesRegex(ValueError, "Query embedding dimension"):
            self.store.search([1.0, 0.0, 0.0])

        self.assertEqual(
            self.store.search([1.0, 0.0]),
            {"ids": [], "documents": [], "metadatas": [], "distances": []},
        )

    def test_fake_uses_milvus_squared_l2_distance(self):
        self.store.ensure_embedding_space("fake", "model-a", 2)
        self.store.add_documents(
            [self._documents()[0]],
            [[0.0, 0.0]],
        )

        results = self.store.search([3.0, 4.0])

        self.assertEqual(results["distances"], [25.0])

    def test_embedding_space_is_persisted_and_incompatible_models_are_rejected(self):
        self.store.ensure_embedding_space("fake", "model-a", 2)
        self.store.add_documents(self._documents(), [[1.0, 0.0], [0.0, 1.0]])

        metadata = self.store.get_collection_info()["metadata"]
        self.assertEqual(metadata["embedding_provider"], "fake")
        self.assertEqual(metadata["embedding_model"], "model-a")
        self.assertEqual(metadata["embedding_dimension"], 2)
        self.store.ensure_embedding_space("fake", "model-a", 2)

        with self.assertRaisesRegex(ValueError, "embedding_model"):
            self.store.ensure_embedding_space("fake", "model-b", 2)
        with self.assertRaisesRegex(ValueError, "dimension"):
            self.store.ensure_embedding_space("fake", "model-a", 3)

    def test_empty_collection_can_reset_to_a_new_embedding_dimension(self):
        self.store.ensure_embedding_space("fake", "model-a", 2)
        self.store.add_documents(self._documents(), [[1.0, 0.0], [0.0, 1.0]])
        self.store.delete_by_document_id("doc-1")

        self.store.ensure_embedding_space("fake", "model-b", 3)
        self.store.add_documents(
            [self._documents()[0]],
            [[1.0, 0.0, 0.0]],
        )

        self.assertEqual(self.store.count(), 1)
        self.assertEqual(
            self.store.get_collection_info()["metadata"]["embedding_dimension"],
            3,
        )

    def test_metadata_filter_and_index_inventory(self):
        documents = self._documents()
        documents[0].metadata["index_id"] = "index-a"
        documents[1].metadata["index_id"] = "index-b"
        self.store.ensure_embedding_space("fake", "model-a", 2)
        self.store.add_documents(documents, [[1.0, 0.0], [0.0, 1.0]])

        results = self.store.search(
            [1.0, 0.0],
            n_results=2,
            where={"index_id": "index-b"},
        )
        self.assertEqual(results["ids"], ["chunk-2"])
        self.assertEqual(
            self.store.index_inventory(),
            ({"index-a": 1, "index-b": 1}, 0),
        )

    def test_write_requires_embedding_space_initialization(self):
        with self.assertRaisesRegex(RuntimeError, "ensure_embedding_space"):
            self.store.add_documents([self._documents()[0]], [[1.0, 0.0]])

    def test_unknown_collection_is_not_replaced(self):
        self.store.client.create_collection(
            collection_name=self.store.collection_name,
            schema=FakeMilvusClient.create_schema(),
            index_params=FakeMilvusClient.prepare_index_params(),
        )
        self.store._collection_ready = True

        with self.assertRaisesRegex(ValueError, "no embedding-space metadata"):
            self.store.ensure_embedding_space("fake", "model-a", 2)
        self.assertTrue(
            self.store.client.has_collection(self.store.collection_name)
        )

        self.store.client.insert(
            collection_name=self.store.collection_name,
            data=[{"id": "foreign-row"}],
        )
        with self.assertRaisesRegex(ValueError, "no embedding-space metadata"):
            self.store.ensure_embedding_space("fake", "model-a", 2)


if __name__ == "__main__":
    unittest.main()
