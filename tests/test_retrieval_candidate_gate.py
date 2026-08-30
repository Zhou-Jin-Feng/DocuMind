import copy
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from evaluation.retrieval_candidate_gate import (
    REPORT_KINDS,
    build_retrieval_candidate_decision,
)
from evaluation.retrieval_candidate_gate_runner import main as candidate_gate_main

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RetrievalCandidateGateTests(unittest.TestCase):
    def setUp(self):
        self.root_context = tempfile.TemporaryDirectory()
        self.root = Path(self.root_context.name)

    def tearDown(self):
        self.root_context.cleanup()

    @staticmethod
    def _cases(recall: float, mrr: float, no_answer: float, p95: float):
        cases = []
        for index in range(20):
            cases.append(
                {
                    "case_id": f"validation-{index:02d}",
                    "question": f"validation question {index}",
                    "top_k": 3,
                    "retrieved_document_ids": ["doc"],
                    "metrics": {
                        "recall_at_k": recall,
                        "no_answer_retrieval_accuracy": None,
                        "mrr_at_k": mrr,
                    },
                    "duration_ms": p95,
                    "status": "success",
                    "category": "validation",
                    "split": "validation",
                }
            )
        for index in range(10):
            is_no_answer = index >= 5
            cases.append(
                {
                    "case_id": f"holdout-{index:02d}",
                    "question": f"holdout question {index}",
                    "top_k": 3,
                    "retrieved_document_ids": [] if is_no_answer else ["doc"],
                    "metrics": {
                        "recall_at_k": None if is_no_answer else recall,
                        "no_answer_retrieval_accuracy": (
                            no_answer if is_no_answer else None
                        ),
                        "mrr_at_k": None if is_no_answer else mrr,
                    },
                    "duration_ms": p95,
                    "status": "success",
                    "category": "no_answer" if is_no_answer else "answerable",
                    "split": "holdout",
                }
            )
        for index in range(5):
            cases.append(
                {
                    "case_id": f"holdout-extra-{index:02d}",
                    "question": f"holdout extra question {index}",
                    "top_k": 3,
                    "retrieved_document_ids": ["doc"],
                    "metrics": {
                        "recall_at_k": recall,
                        "no_answer_retrieval_accuracy": None,
                        "mrr_at_k": mrr,
                    },
                    "duration_ms": p95,
                    "status": "success",
                    "category": "answerable",
                    "split": "holdout",
                }
            )
        return cases

    def _payload(
        self,
        kind: str,
        *,
        recall: float,
        mrr: float,
        no_answer: float,
        p95: float,
    ):
        modes = {
            "dense": ("dense", "baseline", "ollama", "qwen3-embedding", 4096),
            "bm25": ("bm25", "baseline", "none", "none", 0),
            "hybrid": ("hybrid", "baseline", "ollama", "qwen3-embedding", 4096),
            "rerank": ("hybrid", "rerank", "ollama", "qwen3-embedding", 4096),
        }
        retrieval_mode, enhancement_mode, provider, model, dimension = modes[kind]
        holdout_metrics = {
            "recall_at_k": recall,
            "mrr_at_k": mrr,
            "no_answer_retrieval_accuracy": no_answer,
            "successful_case_rate": 1.0,
            "p95_duration_ms": p95,
            "case_count": 15.0,
        }
        return {
            "dataset_name": f"candidate-{kind}",
            "top_k": 3,
            "case_count": 35,
            "metadata": {
                "document_count": 10,
                "chunk_count": 20,
                "embedding_provider": provider,
                "embedding_model": model,
                "embedding_dimension": dimension,
                "chunk_size": 500,
                "chunk_overlap": 100,
                "case_count": 35,
                "case_top_k_values": [3],
                "score_threshold": None,
                "lexical_score_threshold": None,
                "dense_weight": 1.0,
                "lexical_weight": 1.0,
                "rrf_k": 60,
                "candidate_multiplier": 5,
                "retrieval_mode": retrieval_mode,
                "enhancement_mode": enhancement_mode,
                "evaluation_split": "all",
                "dataset_sha256": "a" * 64,
                "documents_sha256": "b" * 64,
                "reranker_model": (
                    "BAAI/bge-reranker-base" if kind == "rerank" else None
                ),
            },
            "metrics": dict(holdout_metrics),
            "split_metrics": {
                "validation": {"case_count": 20.0},
                "holdout": holdout_metrics,
            },
            "cases": self._cases(recall, mrr, no_answer, p95),
        }

    def _write_reports(self, metrics=None):
        values = metrics or {
            "dense": (0.80, 0.70, 0.80, 100.0),
            "bm25": (0.80, 0.75, 0.80, 20.0),
            "hybrid": (0.80, 0.70, 0.80, 120.0),
            "rerank": (0.80, 0.76, 0.80, 180.0),
        }
        paths = {}
        for kind in REPORT_KINDS:
            path = self.root / f"{kind}.json"
            path.write_text(
                json.dumps(
                    self._payload(
                        kind,
                        recall=values[kind][0],
                        mrr=values[kind][1],
                        no_answer=values[kind][2],
                        p95=values[kind][3],
                    )
                ),
                encoding="utf-8",
            )
            paths[kind] = path
        return paths

    def test_selects_best_candidate_when_evidence_and_policy_pass(self):
        decision = build_retrieval_candidate_decision(self._write_reports())

        self.assertEqual(decision.decision, "GO")
        self.assertEqual(decision.selected_candidate, "rerank")
        self.assertTrue(decision.candidates["bm25"].eligible)
        self.assertTrue(decision.candidates["rerank"].eligible)
        self.assertFalse(decision.candidates["hybrid"].eligible)
        self.assertIn(
            "no material holdout quality gain",
            " ".join(decision.candidates["hybrid"].failures),
        )

    def test_exposes_headroom_and_per_case_rank_diagnostics(self):
        paths = self._write_reports(
            {
                "dense": (1.0, 1.0, 0.8, 100.0),
                "bm25": (1.0, 1.0, 0.8, 20.0),
                "hybrid": (1.0, 1.0, 0.8, 120.0),
                "rerank": (1.0, 1.0, 0.8, 180.0),
            }
        )
        payload = json.loads(paths["rerank"].read_text(encoding="utf-8"))
        payload["cases"][20]["retrieved_document_ids"] = ["other", "doc"]
        payload["cases"][20]["metrics"]["mrr_at_k"] = 0.5
        payload["split_metrics"]["holdout"]["mrr_at_k"] = 0.95
        paths["rerank"].write_text(json.dumps(payload), encoding="utf-8")

        decision = build_retrieval_candidate_decision(paths)
        diagnostics = decision.candidates["rerank"].diagnostics

        self.assertEqual(diagnostics["holdout_answerable_case_count"], 10)
        self.assertEqual(diagnostics["baseline_answerable_top1_rate"], 1.0)
        self.assertEqual(diagnostics["candidate_answerable_top1_rate"], 0.9)
        self.assertEqual(diagnostics["answerable_rank_regressions"], 1)
        self.assertEqual(diagnostics["changed_rank_case_count"], 1)
        self.assertEqual(diagnostics["candidate_no_answer_non_empty_rate"], 0.0)
        self.assertIn("diagnostics", decision.to_dict()["candidates"]["rerank"])

    def test_rejects_quality_regression_and_excess_latency(self):
        paths = self._write_reports(
            {
                "dense": (0.80, 0.70, 0.80, 100.0),
                "bm25": (0.70, 0.80, 0.80, 20.0),
                "hybrid": (0.80, 0.75, 0.80, 900.0),
                "rerank": (0.80, 0.80, 0.70, 250.0),
            }
        )
        decision = build_retrieval_candidate_decision(paths)

        self.assertEqual(decision.decision, "NO_GO")
        self.assertIn(
            "recall_at_k regressed", " ".join(decision.candidates["bm25"].failures)
        )
        self.assertIn("P95 increase", " ".join(decision.candidates["hybrid"].failures))
        self.assertIn(
            "no_answer_retrieval_accuracy regressed",
            " ".join(decision.candidates["rerank"].failures),
        )

    def test_rejects_incompatible_case_set_and_small_evidence(self):
        paths = self._write_reports()
        payload = json.loads(paths["hybrid"].read_text(encoding="utf-8"))
        payload["cases"][0]["question"] = "changed"
        paths["hybrid"].write_text(json.dumps(payload), encoding="utf-8")
        dense_payload = json.loads(paths["dense"].read_text(encoding="utf-8"))
        dense_payload["cases"] = [
            *dense_payload["cases"][:7],
            *dense_payload["cases"][20:25],
        ]
        dense_payload["case_count"] = 12
        dense_payload["metadata"]["case_count"] = 12
        dense_payload["split_metrics"]["validation"]["case_count"] = 7.0
        dense_payload["split_metrics"]["holdout"]["case_count"] = 5.0
        dense_payload["split_metrics"]["holdout"]["no_answer_retrieval_accuracy"] = None
        paths["dense"].write_text(json.dumps(dense_payload), encoding="utf-8")

        decision = build_retrieval_candidate_decision(paths)

        self.assertEqual(decision.decision, "NO_GO")
        self.assertTrue(
            any("case_count differs" in item for item in decision.global_failures)
        )
        self.assertTrue(any("total cases" in item for item in decision.global_failures))

    def test_runner_writes_no_go_artifact_and_uses_exit_one(self):
        paths = self._write_reports(
            {kind: (0.80, 0.70, 0.80, 100.0) for kind in REPORT_KINDS}
        )
        json_output = self.root / "decision.json"
        markdown_output = self.root / "decision.md"
        arguments = []
        for kind in REPORT_KINDS:
            arguments.extend((f"--{kind}", str(paths[kind])))
        arguments.extend(
            (
                "--output-json",
                str(json_output),
                "--output-markdown",
                str(markdown_output),
            )
        )
        with redirect_stdout(io.StringIO()) as output:
            exit_code = candidate_gate_main(arguments)

        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(json_output.read_text())["decision"], "NO_GO")
        self.assertIn("P2 retrieval candidate gate", output.getvalue())
        self.assertIn("NO_GO", markdown_output.read_text(encoding="utf-8"))

    def test_source_report_hash_is_stable_across_line_endings(self):
        logical_paths = self._write_reports()
        platform_paths = {}
        for kind, source in logical_paths.items():
            target = self.root / f"{kind}-crlf.json"
            target.write_bytes(source.read_bytes().replace(b"\n", b"\r\n"))
            platform_paths[kind] = target

        logical_decision = build_retrieval_candidate_decision(logical_paths)
        platform_decision = build_retrieval_candidate_decision(platform_paths)

        self.assertEqual(logical_decision.decision, platform_decision.decision)
        for kind in REPORT_KINDS:
            self.assertEqual(
                logical_decision.reports[kind].source_sha256,
                platform_decision.reports[kind].source_sha256,
            )

    def test_rejects_duplicate_fields(self):
        paths = self._write_reports()
        source = paths["dense"].read_text(encoding="utf-8")
        paths["dense"].write_text(
            source.replace('{"dataset_name":', '{"top_k": 3, "dataset_name":', 1),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "duplicate field: top_k"):
            build_retrieval_candidate_decision(paths)

    def test_rejects_inconsistent_split_counts(self):
        paths = self._write_reports()
        payload = json.loads(paths["dense"].read_text(encoding="utf-8"))
        payload["split_metrics"]["holdout"]["case_count"] = 14.0
        paths["dense"].write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "holdout metric case_count"):
            build_retrieval_candidate_decision(paths)

    def test_rejects_aggregate_metric_inconsistent_with_cases(self):
        paths = self._write_reports()
        payload = json.loads(paths["dense"].read_text(encoding="utf-8"))
        payload["split_metrics"]["holdout"]["mrr_at_k"] = 0.123
        paths["dense"].write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "aggregate mrr_at_k is inconsistent"):
            build_retrieval_candidate_decision(paths)

    def test_frozen_real_decision_and_documented_hashes_reproduce(self):
        report_paths = {
            "dense": PROJECT_ROOT
            / "evaluation/reports/p2_1_ollama_threshold_dense.json",
            "bm25": PROJECT_ROOT / "evaluation/reports/p2_1_bm25_threshold.json",
            "hybrid": PROJECT_ROOT
            / "evaluation/reports/p2_1_ollama_threshold_hybrid.json",
            "rerank": PROJECT_ROOT
            / "evaluation/reports/p2_1_ollama_threshold_hybrid_rerank.json",
        }
        decision = build_retrieval_candidate_decision(report_paths)
        expected_json = (
            PROJECT_ROOT
            / "evaluation/baselines/p2_retrieval_candidate_decision_v1.json"
        ).read_text(encoding="utf-8")
        expected_markdown = (
            PROJECT_ROOT / "evaluation/baselines/p2_retrieval_candidate_decision_v1.md"
        ).read_text(encoding="utf-8")

        self.assertEqual(decision.to_json(), expected_json)
        self.assertEqual(decision.to_markdown(), expected_markdown)
        readme = (PROJECT_ROOT / "evaluation/baselines/README.md").read_text(
            encoding="utf-8"
        )
        for content in (expected_json, expected_markdown):
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            self.assertIn(digest, readme)


if __name__ == "__main__":
    unittest.main()
