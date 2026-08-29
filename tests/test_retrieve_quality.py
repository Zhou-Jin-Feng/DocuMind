import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from evaluation.regression_runner import main as regression_main
from evaluation.retrieve_quality import (
    RetrieveQualityCaseResult,
    RetrieveQualityReport,
    _ndcg_at_k,
    load_retrieve_quality_dataset,
    quality_invariant_failures,
    run_retrieve_quality,
)
from evaluation.retrieve_quality_runner import (
    DEFAULT_DATASET,
    main as retrieve_quality_main,
)


class RetrieveQualityTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))

    def write_dataset(self, root: Path, payload=None) -> Path:
        path = root / "dataset.json"
        path.write_text(
            json.dumps(
                self.payload if payload is None else payload, ensure_ascii=False
            ),
            encoding="utf-8",
        )
        return path

    def test_frozen_dataset_exercises_public_service_and_isolation(self):
        dataset = load_retrieve_quality_dataset(DEFAULT_DATASET)
        report = run_retrieve_quality(dataset)

        self.assertEqual(len(dataset.documents), 2)
        self.assertEqual(sum(len(item.chunks) for item in dataset.documents), 6)
        self.assertEqual(len(report.case_results), 5)
        self.assertEqual(quality_invariant_failures(report), ())
        for name in (
            "recall_at_k",
            "mrr_at_k",
            "ndcg_at_k",
            "no_answer_empty_accuracy",
            "api_bottom_parity_rate",
            "contamination_free_rate",
            "successful_case_rate",
        ):
            self.assertEqual(report.metrics[name], 1.0, name)
        self.assertEqual(report.metrics["precision_at_k"], 0.5)
        for result in report.case_results:
            self.assertEqual(
                result.retrieved_chunk_ids,
                result.bottom_retriever_chunk_ids,
            )
            self.assertEqual(result.contamination_count, 0)

    def test_ndcg_uses_rank_discount_and_excludes_empty_targets(self):
        self.assertEqual(_ndcg_at_k([], ["a"], 2), None)
        self.assertEqual(_ndcg_at_k(["a"], ["a", "b"], 2), 1.0)
        self.assertAlmostEqual(_ndcg_at_k(["a"], ["b", "a"], 2), 1 / 1.584962500721156)

    def test_dataset_rejects_duplicate_json_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            source = DEFAULT_DATASET.read_text(encoding="utf-8")
            path.write_text(
                source.replace(
                    '"dataset_name": "documind-retrieve-quality-v1",',
                    '"dataset_name": "first",\n  "dataset_name": "second",',
                    1,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate field"):
                load_retrieve_quality_dataset(path)

    def test_dataset_rejects_unknown_and_out_of_scope_references(self):
        mutations = []

        unknown = copy.deepcopy(self.payload)
        unknown["unknown"] = True
        mutations.append((unknown, "fields differ"))

        wrong_index = copy.deepcopy(self.payload)
        wrong_index["cases"][0]["expected_index_id"] = "d" * 64
        mutations.append((wrong_index, "does not match"))

        foreign_chunk = copy.deepcopy(self.payload)
        foreign_chunk["cases"][0]["relevant_chunk_ids"] = ["4" * 64]
        mutations.append((foreign_chunk, "members of the target document"))

        duplicate_chunk = copy.deepcopy(self.payload)
        duplicate_chunk["documents"][1]["chunks"][0]["chunk_id"] = "1" * 64
        mutations.append((duplicate_chunk, "chunk_id is duplicated"))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for position, (payload, message) in enumerate(mutations):
                with self.subTest(position=position, message=message):
                    path = self.write_dataset(root, payload)
                    with self.assertRaisesRegex(ValueError, message):
                        load_retrieve_quality_dataset(path)

    def test_dataset_requires_positive_and_expected_empty_cases(self):
        no_positive = copy.deepcopy(self.payload)
        no_positive["cases"] = [copy.deepcopy(self.payload["cases"][-1])]
        no_empty = copy.deepcopy(self.payload)
        no_empty["cases"] = copy.deepcopy(self.payload["cases"][:-1])

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for payload, message in (
                (no_positive, "answerable case"),
                (no_empty, "expected-empty case"),
            ):
                with self.subTest(message=message):
                    path = self.write_dataset(root, payload)
                    with self.assertRaisesRegex(ValueError, message):
                        load_retrieve_quality_dataset(path)

    def test_quality_invariants_reject_execution_and_scope_failures(self):
        case = RetrieveQualityCaseResult(
            case_id="failed",
            expected_chunk_ids=("a",),
            retrieved_chunk_ids=(),
            bottom_retriever_chunk_ids=(),
            distances=(),
            recall_at_k=None,
            precision_at_k=None,
            mrr_at_k=None,
            ndcg_at_k=None,
            empty_result_correct=None,
            api_bottom_parity=0.0,
            contamination_count=0,
            duration_ms=1.0,
            status="error",
            error_type="TimeoutError",
        )
        report = RetrieveQualityReport(
            dataset_name="failed",
            top_k=2,
            case_results=(case,),
            metadata={},
            metrics={
                "api_bottom_parity_rate": 0.0,
                "contamination_free_rate": 1.0,
                "no_answer_empty_accuracy": None,
                "successful_case_rate": 0.0,
            },
        )

        failures = quality_invariant_failures(report)

        self.assertTrue(any("case execution failed" in item for item in failures))
        self.assertTrue(any("api_bottom_parity_rate" in item for item in failures))
        self.assertTrue(any("successful_case_rate" in item for item in failures))

    def test_cli_atomically_writes_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            json_output = root / "reports" / "quality.json"
            markdown_output = root / "reports" / "quality.md"
            with redirect_stdout(io.StringIO()) as output:
                result = retrieve_quality_main(
                    [
                        "--dataset",
                        str(DEFAULT_DATASET),
                        "--json-output",
                        str(json_output),
                        "--markdown-output",
                        str(markdown_output),
                    ]
                )

            self.assertEqual(result, 0)
            self.assertIn("PASS", output.getvalue())
            self.assertEqual(
                json.loads(json_output.read_text(encoding="utf-8"))["case_count"],
                5,
            )
            self.assertIn(
                "offline deterministic Dense",
                markdown_output.read_text(encoding="utf-8"),
            )
            self.assertEqual(list((root / "reports").glob("*.tmp")), [])
            with self.assertRaisesRegex(ValueError, "must be different"):
                retrieve_quality_main(
                    [
                        "--json-output",
                        str(json_output),
                        "--markdown-output",
                        str(json_output),
                    ]
                )

    def test_cli_returns_failure_after_writing_diagnostic_report(self):
        dataset = load_retrieve_quality_dataset(DEFAULT_DATASET)
        report = run_retrieve_quality(dataset)
        failed_report = RetrieveQualityReport(
            dataset_name=report.dataset_name,
            top_k=report.top_k,
            case_results=report.case_results,
            metadata=report.metadata,
            metrics={**report.metrics, "api_bottom_parity_rate": 0.0},
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            json_output = root / "quality.json"
            markdown_output = root / "quality.md"
            with (
                patch(
                    "evaluation.retrieve_quality_runner.run_retrieve_quality",
                    return_value=failed_report,
                ),
                redirect_stdout(io.StringIO()) as output,
            ):
                result = retrieve_quality_main(
                    [
                        "--json-output",
                        str(json_output),
                        "--markdown-output",
                        str(markdown_output),
                    ]
                )
            self.assertEqual(result, 1)
            self.assertIn("api_bottom_parity_rate", output.getvalue())
            self.assertTrue(json_output.is_file())
            self.assertTrue(markdown_output.is_file())

    def test_report_is_compatible_with_existing_regression_gate(self):
        dataset = load_retrieve_quality_dataset(DEFAULT_DATASET)
        report = run_retrieve_quality(dataset)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline.json"
            current = root / "current.json"
            baseline.write_text(report.to_json(), encoding="utf-8")
            current.write_text(report.to_json(), encoding="utf-8")
            with redirect_stdout(io.StringIO()) as output:
                result = regression_main(
                    [
                        "--baseline",
                        str(baseline),
                        "--current",
                        str(current),
                        "--allowed-drop",
                        "ndcg_at_k=0",
                        "--minimum",
                        "api_bottom_parity_rate=1",
                        "--minimum",
                        "contamination_free_rate=1",
                        "--minimum",
                        "no_answer_empty_accuracy=1",
                    ]
                )

            self.assertEqual(result, 0)
            self.assertIn("RAG regression gate: PASS", output.getvalue())


if __name__ == "__main__":
    unittest.main()
