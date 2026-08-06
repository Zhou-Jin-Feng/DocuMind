import json
import io
import gc
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from langchain_core.documents import Document

from evaluation.adapters import FakeAnswerAdapter, FakeRetrievalAdapter, RetrieverAdapter
from evaluation import EvaluationRunner as PublicEvaluationRunner
from evaluation.integration import DeterministicEmbeddingClient, build_deterministic_retriever
from evaluation.production import build_indexed_retrieval_adapter, load_text_documents
from evaluation.production_runner import _default_report_stem
from evaluation.fingerprints import file_sha256, text_corpus_sha256
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
from evaluation.regression import (
    EvaluationSnapshot,
    RegressionGate,
    report_compatibility_issues,
)
from evaluation.regression_runner import main as regression_main
from evaluation.runner import EvaluationRunner, load_golden_dataset


class EvaluationTests(unittest.TestCase):
    @staticmethod
    def _snapshot_payload(*, recall=1.0, dataset_sha="dataset", documents_sha="documents"):
        return {
            "dataset_name": "test-dataset",
            "top_k": 3,
            "case_count": 2,
            "metadata": {
                "dataset_sha256": dataset_sha,
                "documents_sha256": documents_sha,
            },
            "metrics": {
                "recall_at_k": recall,
                "successful_case_rate": 1.0,
            },
        }

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

    def test_no_answer_retrieval_accuracy_exposes_irrelevant_hits(self):
        from evaluation.metrics import no_answer_retrieval_accuracy

        self.assertEqual(no_answer_retrieval_accuracy([], [], 3), 1.0)
        self.assertEqual(no_answer_retrieval_accuracy([], ["irrelevant"], 3), 0.0)
        self.assertIsNone(no_answer_retrieval_accuracy(["doc"], [], 3))

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
        self.assertIsNotNone(results[0].distance)

    def test_retriever_adapter_passes_and_validates_score_threshold(self):
        class FakeRetriever:
            def __init__(self):
                self.calls = []

            def retrieve_semantic(self, question, **kwargs):
                self.calls.append((question, kwargs))
                return []

        retriever = FakeRetriever()
        RetrieverAdapter(retriever, score_threshold=1.0).retrieve("q", 3)
        self.assertEqual(
            retriever.calls,
            [("q", {"top_k": 3, "score_threshold": 1.0})],
        )
        with self.assertRaises(ValueError):
            RetrieverAdapter(retriever, score_threshold=-0.1)

    def test_threshold_report_stem_is_distinct_from_baseline(self):
        self.assertEqual(_default_report_stem("ollama", None), "ollama_retrieval_baseline")
        self.assertEqual(_default_report_stem("ollama", 1.0), "ollama_retrieval_threshold_1")
        self.assertEqual(_default_report_stem("ollama", 0.75), "ollama_retrieval_threshold_0_75")

    def test_threshold_can_reject_no_answer_retrieval_results(self):
        class ThresholdRetriever:
            def retrieve_semantic(self, question, top_k, score_threshold=None):
                del question, top_k
                result = type(
                    "Result",
                    (),
                    {
                        "metadata": {"document_id": "irrelevant"},
                        "content": "irrelevant",
                        "distance": 1.5,
                    },
                )()
                return [] if score_threshold is not None and result.distance > score_threshold else [result]

        report = EvaluationRunner(
            RetrieverAdapter(ThresholdRetriever(), score_threshold=1.0)
        ).run([GoldenCase("no-answer", "q", (), should_answer=False)])
        self.assertEqual(report.metrics["no_answer_retrieval_accuracy"], 1.0)

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
            adapter, summary = build_indexed_retrieval_adapter(
                documents,
                embedder,
                store,
                chunker=DocumentChunker(chunk_size=200, chunk_overlap=0),
            )
            report = EvaluationRunner(
                adapter,
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
            self.assertEqual(summary.document_count, 2)
            self.assertEqual(summary.chunk_count, 2)
            self.assertEqual(summary.embedding_dimension, 64)
            self.assertEqual(summary.embedding_provider, "evaluation-fake")
            self.assertEqual(summary.embedding_model, "sha256-token-hash-v1")
            self.assertEqual(summary.chunk_size, 200)
            self.assertEqual(summary.chunk_overlap, 0)
        finally:
            if 'adapter' in locals() and adapter is not None:
                adapter.close()
            store = None
            gc.collect()
            shutil.rmtree(directory, ignore_errors=True)

    def test_load_text_documents_uses_stable_fixture_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "knowledge-base.txt"
            path.write_text("RAG 内容", encoding="utf-8")
            documents = load_text_documents(directory)
        self.assertEqual(documents[0].metadata["document_id"], "knowledge-base")
        self.assertEqual(documents[0].metadata["chunk_id"], "knowledge-base:source")

    def test_evaluation_fingerprints_change_with_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "a.txt"
            second = root / "b.txt"
            first.write_text("alpha", encoding="utf-8")
            second.write_text("beta", encoding="utf-8")
            initial_file_hash = file_sha256(first)
            initial_corpus_hash = text_corpus_sha256(root)
            second.write_text("changed", encoding="utf-8")
            self.assertEqual(file_sha256(first), initial_file_hash)
            self.assertNotEqual(text_corpus_sha256(root), initial_corpus_hash)

    def test_report_compatibility_requires_matching_input_fingerprints(self):
        baseline = EvaluationSnapshot.from_dict(self._snapshot_payload())
        current = EvaluationSnapshot.from_dict(
            self._snapshot_payload(documents_sha="changed")
        )
        issues = report_compatibility_issues(baseline, current)
        self.assertIn("metadata.documents_sha256 不一致", issues)

    def test_regression_cli_uses_distinct_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline_path = root / "baseline.json"
            current_path = root / "current.json"
            baseline_path.write_text(
                json.dumps(self._snapshot_payload()), encoding="utf-8"
            )

            def run(current_payload):
                current_path.write_text(json.dumps(current_payload), encoding="utf-8")
                with redirect_stdout(io.StringIO()):
                    return regression_main(
                        [
                            "--baseline",
                            str(baseline_path),
                            "--current",
                            str(current_path),
                        ]
                    )

            self.assertEqual(run(self._snapshot_payload(recall=0.99)), 0)
            self.assertEqual(run(self._snapshot_payload(recall=0.8)), 1)
            self.assertEqual(run(self._snapshot_payload(dataset_sha="changed")), 2)

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
            FakeRetrievalAdapter({"q": [RetrievedDocument("doc", distance=0.25)]}),
            dataset_name="test",
            metadata={"embedding_model": "test-model", "score_threshold": None},
        ).run([case])
        parsed = json.loads(report.to_json())
        self.assertEqual(parsed["dataset_name"], "test")
        self.assertEqual(parsed["metadata"]["embedding_model"], "test-model")
        self.assertEqual(parsed["cases"][0]["case_id"], "case")
        self.assertEqual(parsed["cases"][0]["retrieved_distances"], [0.25])
        self.assertIn("Run Configuration", report.to_markdown())


if __name__ == "__main__":
    unittest.main()
