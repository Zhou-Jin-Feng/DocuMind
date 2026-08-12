import json
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from langchain_core.documents import Document

from evaluation.adapters import FakeAnswerAdapter, FakeRetrievalAdapter, RetrieverAdapter
from evaluation import EvaluationRunner as PublicEvaluationRunner
from evaluation.comparison import build_evaluation_comparison
from evaluation.integration import DeterministicEmbeddingClient, build_deterministic_retriever
from evaluation.production import (
    build_indexed_retrieval_adapter,
    build_lexical_retrieval_adapter,
    enhance_retrieval_adapter,
    load_text_documents,
)
from evaluation.production_runner import _default_report_stem, main as production_main
from evaluation.fingerprints import file_sha256, text_corpus_sha256
from app.core.document_chunker import DocumentChunker
from app.core.query_rewriter import MappingQueryRewriter, QueryRewriteResult
from app.core.reranker import CrossEncoderReranker
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
    load_evaluation_snapshot,
    report_compatibility_issues,
)
from evaluation.regression_runner import main as regression_main
from evaluation.rewrite_artifacts import (
    RewriteArtifact,
    build_rewrite_artifact,
    load_rewrite_artifact,
)
from tests.fake_vector_store import FakeMilvusClient
from evaluation.runner import EvaluationRunner, _percentile, load_golden_dataset


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
                "embedding_provider": "test",
                "embedding_model": "test-model",
                "embedding_dimension": 64,
                "score_threshold": None,
            },
            "metrics": {
                "recall_at_k": recall,
                "successful_case_rate": 1.0,
            },
        }

    @staticmethod
    def _enhancement_snapshot_payload(mode, *, mrr=0.9, embedding_model="model"):
        return {
            "dataset_name": "ollama-hybrid-retrieval-baseline",
            "top_k": 3,
            "case_count": 12,
            "metadata": {
                "embedding_provider": "ollama",
                "embedding_model": embedding_model,
                "embedding_dimension": 4096,
                "chunk_size": 500,
                "chunk_overlap": 100,
                "case_top_k_values": [3],
                "score_threshold": 1.0,
                "lexical_score_threshold": 12.2,
                "dense_weight": 1.0,
                "lexical_weight": 1.0,
                "rrf_k": 60,
                "candidate_multiplier": 5,
                "retrieval_mode": "hybrid",
                "enhancement_mode": mode,
                "dataset_sha256": "dataset",
                "documents_sha256": "documents",
            },
            "metrics": {
                "recall_at_k": 1.0,
                "mrr_at_k": mrr,
                "no_answer_retrieval_accuracy": 1.0,
                "successful_case_rate": 1.0,
                "average_duration_ms": 100.0,
                "p50_duration_ms": 90.0,
                "p95_duration_ms": 150.0,
                "maximum_duration_ms": 175.0,
            },
        }

    def test_public_runner_export_is_lazy_and_available(self):
        from evaluation.runner import EvaluationRunner

        self.assertIs(PublicEvaluationRunner, EvaluationRunner)

    def test_latency_percentiles_use_linear_interpolation(self):
        values = [10.0, 20.0, 30.0, 40.0]

        self.assertEqual(_percentile(values, 0.5), 25.0)
        self.assertAlmostEqual(_percentile(values, 0.95), 38.5)
        with self.assertRaises(ValueError):
            _percentile([], 0.5)

    def test_golden_case_rejects_unknown_fields_and_normalizes_lists(self):
        case = GoldenCase.from_dict(
            {
                "id": " case-1 ",
                "question": " question ",
                "expected_document_ids": ["doc-a", "doc-a"],
                "expected_keywords": ["RAG"],
                "category": " Semantic_Paraphrase ",
            }
        )
        self.assertEqual(case.id, "case-1")
        self.assertEqual(case.expected_document_ids, ("doc-a",))
        self.assertEqual(case.category, "semantic_paraphrase")
        with self.assertRaises(ValueError):
            GoldenCase.from_dict({"id": "case-2", "question": "q", "typo": True})

    def test_golden_case_split_is_backward_compatible_and_serialized(self):
        legacy = GoldenCase.from_dict({"id": "legacy", "question": "q"})
        holdout = GoldenCase.from_dict(
            {"id": "holdout", "question": "q2", "split": " HOLDOUT "}
        )
        self.assertEqual(legacy.split, "all")
        self.assertEqual(holdout.split, "holdout")
        self.assertEqual(holdout.to_dict()["split"], "holdout")

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

    def test_precision_counts_relevant_document_only_once(self):
        self.assertEqual(
            precision_at_k(["doc"], ["doc", "doc", "other"], 3),
            1 / 3,
        )

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
                category="semantic_paraphrase",
            ),
            GoldenCase(
                id="no-answer",
                question="q2",
                expected_document_ids=(),
                should_answer=False,
                category="no_answer",
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
        self.assertEqual(
            report.category_metrics["semantic_paraphrase"]["recall_at_k"],
            1.0,
        )
        self.assertEqual(
            report.category_metrics["no_answer"]["no_answer_retrieval_accuracy"],
            1.0,
        )
        self.assertIn("Aggregate Metrics", report.to_markdown())
        self.assertIn("Metrics By Category", report.to_markdown())
        self.assertEqual(report.to_dict()["case_count"], 2)

    def test_runner_aggregates_metrics_by_split(self):
        cases = [
            GoldenCase("train", "q1", ("doc-a",), split="train"),
            GoldenCase("holdout", "q2", (), should_answer=False, split="holdout"),
        ]
        retrieval = FakeRetrievalAdapter(
            {"q1": [RetrievedDocument("doc-a")], "q2": []}
        )
        report = EvaluationRunner(retrieval).run(cases)
        self.assertEqual(report.split_metrics["train"]["recall_at_k"], 1.0)
        self.assertEqual(
            report.split_metrics["holdout"]["no_answer_retrieval_accuracy"],
            1.0,
        )
        self.assertEqual(report.case_results[1].split, "holdout")
        self.assertIn("Metrics By Split", report.to_markdown())

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
        with self.assertRaises(ValueError):
            RetrieverAdapter(retriever, score_threshold=float("nan"))

    def test_retriever_adapter_passes_lexical_score_threshold(self):
        class FakeRetriever:
            def __init__(self):
                self.calls = []

            def retrieve_lexical(self, question, **kwargs):
                self.calls.append((question, kwargs))
                return []

        retriever = FakeRetriever()
        RetrieverAdapter(
            retriever,
            retrieval_method="retrieve_lexical",
            lexical_score_threshold=0.25,
        ).retrieve("q", 3)
        self.assertEqual(
            retriever.calls,
            [("q", {"top_k": 3, "lexical_score_threshold": 0.25})],
        )

    def test_threshold_report_stem_is_distinct_from_baseline(self):
        self.assertEqual(_default_report_stem("ollama", None), "ollama_retrieval_baseline")
        self.assertEqual(_default_report_stem("ollama", 1.0), "ollama_retrieval_threshold_1")
        self.assertEqual(_default_report_stem("ollama", 0.75), "ollama_retrieval_threshold_0_75")
        self.assertEqual(
            _default_report_stem("ollama", None, "hybrid"),
            "ollama_hybrid_retrieval_baseline",
        )
        self.assertEqual(
            _default_report_stem(
                "ollama",
                1.0,
                "hybrid",
                lexical_score_threshold=12.2,
            ),
            "ollama_hybrid_retrieval_threshold_1_lex_12_2",
        )
        self.assertEqual(
            _default_report_stem(
                "ollama",
                1.0,
                "hybrid",
                enhancement_mode="rewrite-rerank",
            ),
            "ollama_hybrid_retrieval_threshold_1_rewrite_rerank",
        )

    def test_production_cli_rejects_incompatible_parameters_before_indexing(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            production_main(
                ["--retrieval-mode", "dense", "--lexical-score-threshold", "1.0"]
            )
        self.assertEqual(error.exception.code, 2)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            production_main(["--rerank-candidate-multiplier", "0"])
        self.assertEqual(error.exception.code, 2)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            production_main(["--rewrite-map", "rewrites.json"])
        self.assertEqual(error.exception.code, 2)

    def test_rewrite_artifact_is_strict_and_bound_to_dataset_fingerprint(self):
        cases = [GoldenCase("one", "How does RRF work?", ("doc",))]
        artifact = build_rewrite_artifact(
            cases,
            MappingQueryRewriter(
                {"How does RRF work?": ["reciprocal rank fusion"]}
            ),
            provider="deepseek",
            model="deepseek-chat",
            max_rewrites=2,
            max_tokens=256,
            temperature=0.0,
            prompt_sha256="a" * 64,
            dataset_sha256="b" * 64,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rewrites.json"
            path.write_text(artifact.to_json(), encoding="utf-8")
            loaded = load_rewrite_artifact(
                path,
                expected_dataset_sha256="b" * 64,
                expected_questions=["How does RRF work?"],
            )
            self.assertEqual(
                loaded.to_rewriter().rewrite("How does RRF work?").queries,
                ("How does RRF work?", "reciprocal rank fusion"),
            )
            with self.assertRaisesRegex(ValueError, "生成上限"):
                loaded.to_rewriter(max_rewrites=3)
            with self.assertRaisesRegex(ValueError, "规范化后重复"):
                load_rewrite_artifact(
                    path,
                    expected_dataset_sha256="b" * 64,
                    expected_questions=["How does RRF work?", " How does RRF work? "],
                )
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                load_rewrite_artifact(
                    path,
                    expected_dataset_sha256="c" * 64,
                    expected_questions=["How does RRF work?"],
                )
            path.write_text(
                '{"provider":"deepseek","model":"model","max_rewrites":1,'
                f'"dataset_sha256":"{"b" * 64}","rewrites":{{}},"rewrites":{{}}}}',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_rewrite_artifact(
                    path,
                    expected_dataset_sha256="b" * 64,
                    expected_questions=[],
                )
        with self.assertRaises(ValueError):
            RewriteArtifact.from_dict(
                {
                    "artifact_version": 1,
                    "provider": "deepseek",
                    "model": "model",
                    "max_rewrites": 1,
                    "max_tokens": 256,
                    "temperature": 0.0,
                    "prompt_sha256": "a" * 64,
                    "dataset_sha256": "b" * 64,
                    "rewrites": {},
                    "unexpected": True,
                }
            )
        with self.assertRaises(ValueError):
            RewriteArtifact(
                artifact_version=True,
                provider="deepseek",
                model="model",
                max_rewrites=2,
                max_tokens=256,
                temperature=0.0,
                prompt_sha256="a" * 64,
                dataset_sha256="b" * 64,
                rewrites={},
            )

    def test_enhanced_adapter_records_query_fusion_and_rerank_scores(self):
        retriever = build_deterministic_retriever(
            [
                Document(
                    page_content="RAG uses retrieval augmented generation.",
                    metadata={"document_id": "rag", "chunk_id": "rag:1"},
                ),
                Document(
                    page_content="Weather forecasts contain temperature.",
                    metadata={"document_id": "weather", "chunk_id": "weather:1"},
                ),
            ]
        )

        class KeywordModel:
            def predict(self, pairs, **kwargs):
                del kwargs
                return [1.0 if "RAG" in content else 0.0 for _, content in pairs]

        adapter = RetrieverAdapter(retriever)
        enhance_retrieval_adapter(
            adapter,
            query_rewriter=MappingQueryRewriter(
                {"how does retrieval augmentation work": ["RAG retrieval"]}
            ),
            reranker=CrossEncoderReranker(
                "fake/model",
                model_factory=lambda *args, **kwargs: KeywordModel(),
            ),
            rerank_candidate_multiplier=2,
        )
        try:
            documents = adapter.retrieve("how does retrieval augmentation work", 1)
        finally:
            adapter.close()

        self.assertEqual(documents[0].document_id, "rag")
        self.assertIsNotNone(documents[0].query_fusion_score)
        self.assertEqual(documents[0].rerank_score, 1.0)

    def test_lexical_adapter_preserves_document_ids_without_distances(self):
        adapter, summary = build_lexical_retrieval_adapter(
            [
                Document(
                    page_content="RRF 使用倒数排名融合",
                    metadata={"document_id": "retrieval-quality"},
                )
            ],
            chunker=DocumentChunker(chunk_size=200, chunk_overlap=0),
        )

        documents = adapter.retrieve("RRF 排名融合", 3)

        self.assertEqual([item.document_id for item in documents], ["retrieval-quality"])
        self.assertIsNone(documents[0].distance)
        self.assertEqual(summary.embedding_provider, "none")
        adapter.close()

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
                return (
                    []
                    if score_threshold is not None
                    and result.distance > score_threshold
                    else [result]
                )

        report = EvaluationRunner(
            RetrieverAdapter(ThresholdRetriever(), score_threshold=1.0)
        ).run([GoldenCase("no-answer", "q", (), should_answer=False)])
        self.assertEqual(report.metrics["no_answer_retrieval_accuracy"], 1.0)

    def test_milvus_pipeline_reaches_runner_metrics_without_network(self):
        client_patcher = patch(
            "app.core.vector_store.MilvusClient",
            FakeMilvusClient,
        )
        client_patcher.start()
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
                uri="http://milvus.test:19530",
                db_name="unit_test",
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
                        id="milvus-rag",
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
            client_patcher.stop()

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

        changed_model_payload = self._snapshot_payload()
        changed_model_payload["metadata"]["embedding_model"] = "different"
        changed_model = EvaluationSnapshot.from_dict(changed_model_payload)
        issues = report_compatibility_issues(baseline, changed_model)
        self.assertIn("metadata.embedding_model 不一致", issues)

    def test_snapshot_loader_rejects_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.json"
            report.write_text(
                '{"dataset_name":"a","dataset_name":"b","top_k":3,'
                '"case_count":1,"metadata":{},"metrics":{}}',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "重复字段"):
                load_evaluation_snapshot(report)

    def test_four_mode_comparison_requires_matching_configuration(self):
        snapshots = {
            mode: EvaluationSnapshot.from_dict(
                self._enhancement_snapshot_payload(
                    mode,
                    mrr=1.0 if mode in {"rerank", "rewrite-rerank"} else 0.9,
                )
            )
            for mode in ("baseline", "rewrite", "rerank", "rewrite-rerank")
        }

        comparison = build_evaluation_comparison(snapshots)

        self.assertAlmostEqual(
            comparison.deltas_from_baseline["rerank"]["mrr_at_k"],
            0.1,
        )
        self.assertIn("precision_at_k", comparison.metrics_by_mode["baseline"])
        self.assertIn("top_k_hit_rate", comparison.metrics_by_mode["baseline"])
        self.assertIn("Quality And Latency", comparison.to_markdown())
        incompatible = dict(snapshots)
        incompatible["rewrite"] = EvaluationSnapshot.from_dict(
            self._enhancement_snapshot_payload(
                "rewrite",
                embedding_model="different-model",
            )
        )
        with self.assertRaisesRegex(ValueError, "embedding_model"):
            build_evaluation_comparison(incompatible)

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
        self.assertEqual(parsed["cases"][0]["retrieved_rerank_scores"], [None])
        self.assertIn("p50_duration_ms", parsed["metrics"])
        self.assertIn("p95_duration_ms", parsed["metrics"])
        self.assertIn("maximum_duration_ms", parsed["metrics"])
        self.assertIn("Run Configuration", report.to_markdown())


    def test_rewrite_artifact_rejects_normalized_duplicates(self):
        with self.assertRaises(ValueError):
            RewriteArtifact(
                artifact_version=1,
                provider="deepseek",
                model="model",
                max_rewrites=2,
                max_tokens=256,
                temperature=0.0,
                prompt_sha256="a" * 64,
                dataset_sha256="b" * 64,
                rewrites={"q": ["alternative"], " q ": ["other"]},
            )
        with self.assertRaises(ValueError):
            RewriteArtifact(
                artifact_version=1,
                provider="deepseek",
                model="model",
                max_rewrites=2,
                max_tokens=256,
                temperature=0.0,
                prompt_sha256="a" * 64,
                dataset_sha256="b" * 64,
                rewrites={"q": ["alternative", " ALTERNATIVE "]},
            )
        with self.assertRaises(TypeError):
            RewriteArtifact(
                artifact_version=1,
                provider="deepseek",
                model="model",
                max_rewrites=2,
                max_tokens=256,
                temperature=0.0,
                prompt_sha256="a" * 64,
                dataset_sha256="b" * 64,
                rewrites=[],
            )

    def test_rewrite_artifact_generation_resumes_existing_cases(self):
        cases = [
            GoldenCase("one", "问题一", ("doc",)),
            GoldenCase("two", "问题二", ("doc",)),
        ]

        class CountingRewriter:
            def __init__(self):
                self.calls = []

            def rewrite(self, question):
                self.calls.append(question)
                return QueryRewriteResult.from_candidates(
                    question,
                    [question + " 改写"],
                    max_rewrites=2,
                )

        rewriter = CountingRewriter()
        progress = []
        artifact = build_rewrite_artifact(
            cases,
            rewriter,
            provider="deepseek",
            model="deepseek-chat",
            max_rewrites=2,
            max_tokens=256,
            temperature=0.0,
            prompt_sha256="a" * 64,
            dataset_sha256="b" * 64,
            existing_rewrites={"问题一": ["问题一 已生成"]},
            progress_callback=lambda current, completed, total: progress.append(
                (len(current.rewrites), completed, total)
            ),
        )

        self.assertEqual(rewriter.calls, ["问题二"])
        self.assertEqual(progress, [(2, 2, 2)])
        self.assertEqual(set(artifact.rewrites), {"问题一", "问题二"})


if __name__ == "__main__":
    unittest.main()
