import gc
import shutil
import tempfile
import unittest
from pathlib import Path

from langchain_core.documents import Document

from app.core.vector_store import VectorStore


class VectorStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="rag-vector-test-"))
        self.store = VectorStore(
            collection_name="unit_test_documents",
            persist_directory=str(self.directory),
        )

    def tearDown(self):
        self.store = None
        gc.collect()
        shutil.rmtree(self.directory, ignore_errors=True)

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
        self.store.add_documents(documents, embeddings)
        self.store.add_documents(documents, embeddings)
        self.assertEqual(self.store.collection.count(), 2)

        results = self.store.search([1.0, 0.0], n_results=10)
        self.assertEqual(len(results["documents"]), 2)
        self.assertEqual(len(results["distances"]), 2)

        self.store.delete_by_document_id("doc-1")
        self.assertEqual(self.store.collection.count(), 0)
        self.assertEqual(
            self.store.search([1.0, 0.0]),
            {"ids": [], "documents": [], "metadatas": [], "distances": []},
        )

    def test_embedding_count_and_dimensions_are_validated(self):
        documents = self._documents()
        with self.assertRaises(ValueError):
            self.store.add_documents(documents, [[1.0, 0.0]])
        with self.assertRaisesRegex(ValueError, "维度"):
            self.store.add_documents(documents, [[1.0], [1.0, 0.0]])


if __name__ == "__main__":
    unittest.main()
