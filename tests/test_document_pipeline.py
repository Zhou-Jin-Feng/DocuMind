import tempfile
import unittest
from pathlib import Path

from langchain_core.documents import Document

from app.core.document_chunker import DocumentChunker
from app.core.document_loader import UniversalDocumentLoader


class DocumentPipelineTests(unittest.TestCase):
    def test_txt_load_and_chunk_ids_are_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "知识库.txt"
            file_path.write_text("第一段介绍RAG系统。\n\n第二段介绍向量检索。" * 5, encoding="utf-8")

            loader = UniversalDocumentLoader()
            first_documents = loader.load_document(str(file_path))
            second_documents = loader.load_document(str(file_path))
            self.assertEqual(
                first_documents[0].metadata["document_id"],
                second_documents[0].metadata["document_id"],
            )
            self.assertEqual(first_documents[0].metadata["source"], "知识库.txt")
            self.assertNotIn(str(file_path.parent), first_documents[0].metadata["source"])

            chunker = DocumentChunker(chunk_size=40, chunk_overlap=5)
            first_chunks = chunker.chunk_documents_recursive(first_documents)
            second_chunks = chunker.chunk_documents_recursive(second_documents)
            self.assertTrue(first_chunks)
            self.assertEqual(
                [chunk.metadata["chunk_id"] for chunk in first_chunks],
                [chunk.metadata["chunk_id"] for chunk in second_chunks],
            )
            self.assertEqual(
                [chunk.metadata["chunk_index"] for chunk in first_chunks],
                list(range(len(first_chunks))),
            )
            self.assertTrue(all(chunk.page_content.strip() for chunk in first_chunks))

    def test_gb18030_txt_is_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "gb.txt"
            file_path.write_bytes("中文编码测试".encode("gb18030"))
            documents = UniversalDocumentLoader().load_document(str(file_path))
            self.assertEqual(documents[0].page_content, "中文编码测试")

    def test_doc_extension_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "legacy.doc"
            file_path.write_bytes(b"not a docx")
            with self.assertRaises(ValueError):
                UniversalDocumentLoader().load_document(str(file_path))

    def test_pdf_page_metadata_is_one_based(self):
        documents = [Document(page_content="内容", metadata={"page": 0})]
        UniversalDocumentLoader._normalize_metadata(
            documents,
            "demo.pdf",
            ".pdf",
            "document-id",
        )
        self.assertEqual(documents[0].metadata["page_number"], 1)


if __name__ == "__main__":
    unittest.main()
