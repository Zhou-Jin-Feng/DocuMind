from __future__ import annotations

import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.retriever import RetrievalResult
from evaluation.da02_diagnostic import _source_locations, summarize_case
from evaluation.ds06_runner import Corpus, FrozenCase, Qrel
from langchain_core.documents import Document


class Da02DiagnosticTests(unittest.TestCase):
    def test_source_locations_distinguish_source_and_chunk_hashes(self):
        source_text = "alpha beta gamma"
        chunk_text = "beta"
        with TemporaryDirectory() as temp_dir:
            dataset_root = Path(temp_dir)
            documents_root = dataset_root / "documents"
            documents_root.mkdir()
            (documents_root / "source.txt").write_text(source_text, encoding="utf-8")
            corpus = Corpus(
                documents=(
                    Document(
                        page_content=source_text,
                        metadata={
                            "document_id": "doc-1",
                            "source_file": "source.txt",
                        },
                    ),
                ),
                chunks=(
                    Document(
                        page_content=chunk_text,
                        metadata={
                            "chunk_id": "chunk-1",
                            "chunk_index": 0,
                            "document_id": "doc-1",
                            "source_file": "source.txt",
                        },
                    ),
                ),
                document_count=1,
                chunk_count=1,
                document_sha256="unused",
                chunk_sha256="unused",
            )

            location = _source_locations(dataset_root, corpus)["chunk-1"]

        self.assertEqual(location["source_start"], 6)
        self.assertEqual(location["source_end"], 10)
        self.assertEqual(
            location["source_sha256"],
            hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(
            location["chunk_sha256"],
            hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
        )

    def test_contextual_grade_is_not_counted_as_primary_hit(self):
        case = FrozenCase(
            case_id="REP-T16-03",
            question="度量冲突时采用哪一个？",
            split="holdout",
            category="difficult_negative",
            answerable=True,
            qrels=(
                Qrel(document_id="active-doc", chunk_id="active-chunk", grade=3),
                Qrel(document_id="draft-doc", chunk_id="draft-chunk", grade=1),
            ),
        )
        results = [
            RetrievalResult(
                content="draft evidence",
                metadata={"document_id": "draft-doc", "chunk_id": "draft-chunk"},
                distance=0.1,
                rank=1,
            ),
            RetrievalResult(
                content="unrelated",
                metadata={"document_id": "other-doc", "chunk_id": "other-chunk"},
                distance=0.2,
                rank=2,
            ),
        ]

        report = summarize_case(case, results, top_k=3, locations={})

        self.assertEqual(report["ranked"][0]["evidence_label"], "contextual")
        self.assertEqual(report["metrics"]["contextual_first_rank_at_3"], 1)
        self.assertIsNone(report["metrics"]["primary_first_rank_at_3"])
        self.assertEqual(report["observations"]["contextual_only_in_top3"], True)
        self.assertEqual(report["observations"]["primary_in_top20"], False)


if __name__ == "__main__":
    unittest.main()
