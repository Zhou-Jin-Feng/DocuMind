import json
import gc
import shutil
import tempfile
import unittest
from pathlib import Path

from langchain_core.documents import Document

from evaluation.adapters import FakeAnswerAdapter, FakeRetrievalAdapter, RetrieverAdapter
from evaluation import EvaluationRunner as PublicEvaluationRunner
from evaluation.integration import DeterministicEmbeddingClient, build_deterministic_retriever
from app.core.document_chunker import DocumentChunker
from app.core.retriever import Retriever
from app.core.vector_store import VectorStore
from evaluation.metrics import (
    first_relevant_rank,
    hit_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank_at_k,
)
from evaluation.models import AnswerResult, EvaluationReport, GoldenCase, RetrievedDocument
from evaluation.regression import RegressionGate
from evaluation.runner import EvaluationRunner, load_golden_dataset


class EvaluationTests(unittest.TestCase):
    def test_public_runner_export_is_lazy_and_available(self):
        from evaluation.runner import EvaluationRunner

        self.assertIs(PublicEvaluationRunner, EvaluationRunner)

    def test_golden_case_rejects_unknown_fields_and_normalizes_lists(self):
        case = GoldenCase.from_dict(
            {
                "id": " case-1 ",
                "question": " question ",
                "expected_document_ids": ["doc-a", "doc-a"],
                "expected_keywords": ["RAG"],
            }
        )
        self.assertEqual(case.id, "case-1")
        self.assertEqual(case.expected_document_ids, ("doc-a",))
        with self.assertRaises(ValueError):
            GoldenCase.from_dict({"id": "case-2", "question": "q", "typo": True})

    def test_dataset_loader_rejects_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "golden.jsonl"
            payload = {"id": "same", "question": "q", "expected_document_ids": []}
            path.write_text(
                json.dumps(payload) + "\n" + json.dumps(payload) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "重复"):
                load_golden_dataset(path)

    def test_retrieval_metrics_use_top_k_and_exclude_no_answer_target(self):
        expected = ["doc-a", "doc-b"]
        retrieved = ["doc-x", "doc-b", "doc-a"]
        self.assertEqual(recall_at_k(expected, retrieved, 2), 0.5)
        self.assertEqual(precision_at_k(expected, retrieved, 2), 0.5)
        self.assertEqual(reciprocal_rank_at_k(expected, retrieved, 2), 0.5)
        self.assertEqual(hit_at_k(expected, retrieved, 2), 1.0)
        self.assertEqual(first_relevant_rank(expected, retrieved, 2), 2.0)
        self.assertIsNone(recall_at_k([], retrieved, 2))

    def test_runner_produces_retrieval_and_refusal_metrics(self):
        cases = [
            GoldenCase(
                id="answerable",
                question="q1",
                expected_document_ids=("doc-a",),
                expected_keywords=("answer",),
                should_answer=True,
            ),
            GoldenCase(
                id="no-answer",
                question="q2",
                expected_document_ids=(),
                should_answer=False,
            ),
        ]
        retrieval = FakeRetrievalAdapter(
            {
                "q1": [RetrievedDocument("doc-a", content="answer")],
                "q2": [],
            }
        )
        answers = FakeAnswerAdapter({"q1": AnswerResult(True, "answer"), "q2": False})
        report = EvaluationRunner(retrieval, answers).run(cases)
        self.assertEqual(report.metrics["recall_at_k"], 1.0)
        self.assertEqual(report.metrics["mrr_at_k"], 1.0)
        self.assertEqual(report.metrics["refusal_accuracy"], 1.0)
        self.assertEqual(report.metrics["keyword_coverage"], 1.0)
        self.assertEqual(report.metrics["successful_case_rate"], 1.0)
        self.assertIn("Aggregate Metrics", report.to_markdown())
        self.assertEqual(report.to_dict()["case_count"], 2)

    def test_runner_records_adapter_failure_without_aborting_dataset(self):
        class BrokenAdapter:
            def retrieve(self, question, top_k):
                if question == "broken":
                    raise TimeoutError("offline failure")
                return [RetrievedDocument("doc-a")]

        cases = [
            GoldenCase("ok", "ok", ("doc-a",)),
            GoldenCase("broken", "broken", ("doc-a",)),
        ]
        report = EvaluationRunner(BrokenAdapter()).run(cases)
        self.assertEqual(report.metrics["successful_case_rate"], 0.5)
        self.assertEqual(report.case_results[1].status, "error")
        self.assertEqual(report.case_results[1].error_type, "TimeoutError")

    def test_retriever_adapter_requires_stable_document_id(self):
        class FakeRetriever:
            def retrieve_semantic(self, question, top_k):
                del question, top_k
                return [type("Result", (), {"metadata": {}, "content": "text"})()]

        with self.assertRaises(ValueError):
            RetrieverAdapter(FakeRetriever()).retrieve("q", 1)

    def test_production_retriever_adapter_runs_deterministic_integration(self):
        retriever = build_deterministic_retriever(
            [
                Document(
                    page_content="RAG 使用向量检索增强生成。",
                    metadata={"document_id": "knowledge-base", "chunk_id": "chunk-1"},
                ),
                Document(
                    page_content="天气预报与出行建议。",
                    metadata={"document_id": "weather", "chunk_id": "chunk-2"},
                ),
            ]
        )
        results = RetrieverAdapter(retriever).retrieve("RAG 向量检索", 1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].document_id, "knowledge-base")

    def test_chroma_pipeline_reaches_runner_metrics_without_network(self):
        directory = Path(tempfile.mkdtemp(prefix="rag-evaluation-chroma-"))
        store = None
        try:
            documents = [
                Document(
                    page_content="RAG 使用向量数据库保存 Embedding，并通过检索增强生成。",
                    metadata={"document_id": "knowledge-base", "source_file": "knowledge.txt"},
                ),
                Document(
                    page_content="天气预报用于查询温度、降雨和出行建议。",
                    metadata={"document_id": "weather", "source_file": "weather.txt"},
                ),
            ]
            chunks = DocumentChunker(chunk_size=200, chunk_overlap=0).chunk_documents_recursive(
                documents
            )
            embedder = DeterministicEmbeddingClient()
            store = VectorStore(
                collection_name="evaluation_documents",
                persist_directory=str(directory),
            )
            store.add_documents(chunks, [embedder.embed_text(chunk.page_content) for chunk in chunks])
            report = EvaluationRunner(
                RetrieverAdapter(Retriever(store, embedder)),
                FakeAnswerAdapter({"RAG 如何使用向量数据库？": True}),
            ).run(
                [
                    GoldenCase(
                        id="chroma-rag",
                        question="RAG 如何使用向量数据库？",
                        expected_document_ids=("knowledge-base",),
                        should_answer=True,
                    )
                ]
            )
            self.assertEqual(report.metrics["recall_at_k"], 1.0)
            self.assertEqual(report.metrics["top_k_hit_rate"], 1.0)
            self.assertEqual(report.metrics["successful_case_rate"], 1.0)
        finally:
            store = None
            gc.collect()
            shutil.rmtree(directory, ignore_errors=True)

    def test_regression_gate_checks_drop_and_minimum(self):
        baseline = {"recall_at_k": 0.9, "successful_case_rate": 1.0}
        current = {"recall_at_k": 0.86, "successful_case_rate": 1.0}
        gate = RegressionGate(
            allowed_drops={"recall_at_k": 0.02},
            minimums={"successful_case_rate": 1.0},
        )
        result = gate.evaluate(baseline, current)
        self.assertFalse(result.passed)
        self.assertEqual(result.failures[0].metric, "recall_at_k")
        with self.assertRaises(AssertionError):
            result.assert_passed()

    def test_report_round_trip_shape_is_json_serializable(self):
        case = GoldenCase("case", "q", ("doc",))
        report = EvaluationRunner(
            FakeRetrievalAdapter({"q": [RetrievedDocument("doc")]}),
            dataset_name="test",
        ).run([case])
        parsed = json.loads(report.to_json())
        self.assertEqual(parsed["dataset_name"], "test")
        self.assertEqual(parsed["cases"][0]["case_id"], "case")


if __name__ == "__main__":
    unittest.main()
