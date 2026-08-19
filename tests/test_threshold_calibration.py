import json
import tempfile
import unittest
from pathlib import Path

from evaluation.fingerprints import text_file_sha256
from evaluation.models import GoldenCase
from evaluation.production_runner import _select_cases_by_split
from evaluation.threshold_calibration import (
    SELECTION_POLICY,
    adjacent_midpoint_candidates,
    build_holdout_decision,
    build_validation_calibration,
    calibration_to_json,
    calibration_to_markdown,
    load_json_object,
)
from evaluation.threshold_runner import main as threshold_main


class ThresholdCalibrationTests(unittest.TestCase):
    DATASET_SHA = "a" * 64
    DOCUMENTS_SHA = "b" * 64

    @staticmethod
    def _cases(split="validation"):
        prefix = "val" if split == "validation" else "holdout"
        return [
            GoldenCase(
                f"{prefix}-positive",
                f"{prefix} positive question",
                ("positive-doc",),
                should_answer=True,
                split=split,
            ),
            GoldenCase(
                f"{prefix}-negative-1",
                f"{prefix} negative question 1",
                should_answer=False,
                split=split,
            ),
            GoldenCase(
                f"{prefix}-negative-2",
                f"{prefix} negative question 2",
                should_answer=False,
                split=split,
            ),
        ]

    @classmethod
    def _report(cls, cases, distances_by_id, *, split):
        results = []
        for case in cases:
            distances = distances_by_id[case.id]
            document_ids = [
                (
                    "positive-doc"
                    if case.should_answer and index == 0
                    else f"noise-{index}"
                )
                for index in range(len(distances))
            ]
            results.append(
                {
                    "case_id": case.id,
                    "question": case.question,
                    "top_k": case.top_k,
                    "retrieved_document_ids": document_ids,
                    "retrieved_distances": distances,
                    "status": "success",
                }
            )
        return {
            "dataset_name": "threshold-test",
            "top_k": 3,
            "case_count": len(cases),
            "metadata": {
                "embedding_provider": "ollama",
                "embedding_model": "qwen3-embedding",
                "embedding_dimension": 4096,
                "chunk_size": 500,
                "chunk_overlap": 100,
                "case_top_k_values": [3],
                "score_threshold": None,
                "retrieval_mode": "dense",
                "enhancement_mode": "baseline",
                "distance_metric": "L2",
                "evaluation_split": split,
                "dataset_sha256": cls.DATASET_SHA,
                "documents_sha256": cls.DOCUMENTS_SHA,
            },
            "cases": results,
        }

    @classmethod
    def _passing_validation(cls):
        cases = cls._cases("validation")
        report = cls._report(
            cases,
            {
                "val-positive": [0.10, 0.40],
                "val-negative-1": [0.20, 0.50],
                "val-negative-2": [0.30, 0.60],
            },
            split="validation",
        )
        calibration = build_validation_calibration(
            cases,
            report,
            dataset_sha256=cls.DATASET_SHA,
            source_report_path="validation.json",
            source_report_sha256="c" * 64,
            generated_at="2026-08-19T00:00:00Z",
        )
        return cases, report, calibration

    def test_adjacent_midpoints_are_sorted_unique_and_validate_input(self):
        self.assertEqual(
            adjacent_midpoint_candidates([0.3, 0.1, 0.1, 0.2]),
            (0.15000000000000002, 0.25),
        )
        with self.assertRaises(TypeError):
            adjacent_midpoint_candidates([True])
        with self.assertRaises(ValueError):
            adjacent_midpoint_candidates([float("nan")])

    def test_validation_selects_largest_candidate_that_passes_all_constraints(self):
        _, _, calibration = self._passing_validation()

        self.assertEqual(calibration["selection_policy"], SELECTION_POLICY)
        self.assertAlmostEqual(calibration["selected_threshold"], 0.15)
        self.assertTrue(calibration["validation_passed"])
        passing = [
            row["threshold"]
            for row in calibration["candidates"]
            if row["passes_constraints"]
        ]
        self.assertEqual(passing, [calibration["selected_threshold"]])
        selected = next(
            row
            for row in calibration["candidates"]
            if row["threshold"] == calibration["selected_threshold"]
        )
        self.assertEqual(selected["metrics"]["no_answer_retrieval_accuracy"], 1.0)
        self.assertEqual(selected["metrics"]["answerable_recall_at_k"], 1.0)

    def test_validation_returns_do_not_enable_when_no_candidate_passes(self):
        cases = self._cases("validation")
        report = self._report(
            cases,
            {
                "val-positive": [0.30],
                "val-negative-1": [0.10],
                "val-negative-2": [0.20],
            },
            split="validation",
        )

        calibration = build_validation_calibration(
            cases,
            report,
            dataset_sha256=self.DATASET_SHA,
            source_report_path="validation.json",
            source_report_sha256="c" * 64,
            generated_at="2026-08-19T00:00:00Z",
        )

        self.assertIsNone(calibration["selected_threshold"])
        self.assertEqual(calibration["decision"], "do_not_enable")
        self.assertEqual(
            calibration["holdout_status"], "not_run_no_validation_candidate"
        )
        self.assertFalse(calibration["enable_reference_threshold"])
        self.assertTrue(calibration["code_default_remains_none"])

    def test_report_validation_rejects_thresholded_errors_and_unsorted_distances(self):
        cases = self._cases("validation")
        report = self._report(
            cases,
            {
                "val-positive": [0.10],
                "val-negative-1": [0.20],
                "val-negative-2": [0.30],
            },
            split="validation",
        )
        report["metadata"]["score_threshold"] = 0.2
        with self.assertRaisesRegex(ValueError, "无阈值"):
            build_validation_calibration(
                cases,
                report,
                dataset_sha256=self.DATASET_SHA,
                source_report_path="validation.json",
                source_report_sha256="c" * 64,
                generated_at="2026-08-19T00:00:00Z",
            )
        report["metadata"]["score_threshold"] = None
        report["cases"][0]["retrieved_distances"] = [0.4, 0.1]
        report["cases"][0]["retrieved_document_ids"] = ["positive-doc", "noise"]
        with self.assertRaisesRegex(ValueError, "升序"):
            build_validation_calibration(
                cases,
                report,
                dataset_sha256=self.DATASET_SHA,
                source_report_path="validation.json",
                source_report_sha256="c" * 64,
                generated_at="2026-08-19T00:00:00Z",
            )

    def test_holdout_uses_frozen_candidate_and_can_reject_enablement(self):
        validation_cases, _, calibration = self._passing_validation()
        holdout_cases = self._cases("holdout")
        passing_report = self._report(
            holdout_cases,
            {
                "holdout-positive": [0.12],
                "holdout-negative-1": [0.25],
                "holdout-negative-2": [0.35],
            },
            split="holdout",
        )
        all_cases = validation_cases + holdout_cases

        decision = build_holdout_decision(
            calibration,
            all_cases,
            passing_report,
            dataset_sha256=self.DATASET_SHA,
            validation_calibration_path="scan.json",
            validation_calibration_sha256="d" * 64,
            source_report_path="holdout.json",
            source_report_sha256="e" * 64,
            generated_at="2026-08-19T00:01:00Z",
        )

        self.assertTrue(decision["enable_reference_threshold"])
        self.assertTrue(decision["code_default_remains_none"])
        failing_report = self._report(
            holdout_cases,
            {
                "holdout-positive": [0.18],
                "holdout-negative-1": [0.25],
                "holdout-negative-2": [0.35],
            },
            split="holdout",
        )
        rejected = build_holdout_decision(
            calibration,
            all_cases,
            failing_report,
            dataset_sha256=self.DATASET_SHA,
            validation_calibration_path="scan.json",
            validation_calibration_sha256="d" * 64,
            source_report_path="holdout.json",
            source_report_sha256="e" * 64,
            generated_at="2026-08-19T00:01:00Z",
        )
        self.assertFalse(rejected["holdout_passed"])
        self.assertEqual(rejected["decision"], "do_not_enable")

    def test_holdout_rejects_tampered_selection_and_incompatible_configuration(self):
        validation_cases, _, calibration = self._passing_validation()
        holdout_cases = self._cases("holdout")
        report = self._report(
            holdout_cases,
            {
                "holdout-positive": [0.12],
                "holdout-negative-1": [0.25],
                "holdout-negative-2": [0.35],
            },
            split="holdout",
        )
        tampered = dict(calibration)
        tampered["selected_threshold"] = 0.25
        with self.assertRaisesRegex(ValueError, "通过候选"):
            build_holdout_decision(
                tampered,
                validation_cases + holdout_cases,
                report,
                dataset_sha256=self.DATASET_SHA,
                validation_calibration_path="scan.json",
                validation_calibration_sha256="d" * 64,
                source_report_path="holdout.json",
                source_report_sha256="e" * 64,
                generated_at="2026-08-19T00:01:00Z",
            )
        report["metadata"]["embedding_model"] = "other"
        with self.assertRaisesRegex(ValueError, "不兼容"):
            build_holdout_decision(
                calibration,
                validation_cases + holdout_cases,
                report,
                dataset_sha256=self.DATASET_SHA,
                validation_calibration_path="scan.json",
                validation_calibration_sha256="d" * 64,
                source_report_path="holdout.json",
                source_report_sha256="e" * 64,
                generated_at="2026-08-19T00:01:00Z",
            )

    def test_holdout_is_blocked_when_validation_has_no_candidate(self):
        validation_cases = self._cases("validation")
        validation_report = self._report(
            validation_cases,
            {
                "val-positive": [0.30],
                "val-negative-1": [0.10],
                "val-negative-2": [0.20],
            },
            split="validation",
        )
        calibration = build_validation_calibration(
            validation_cases,
            validation_report,
            dataset_sha256=self.DATASET_SHA,
            source_report_path="validation.json",
            source_report_sha256="c" * 64,
            generated_at="2026-08-19T00:00:00Z",
        )
        holdout_cases = self._cases("holdout")
        holdout_report = self._report(
            holdout_cases,
            {
                "holdout-positive": [0.12],
                "holdout-negative-1": [0.25],
                "holdout-negative-2": [0.35],
            },
            split="holdout",
        )

        with self.assertRaisesRegex(ValueError, "没有冻结候选阈值"):
            build_holdout_decision(
                calibration,
                validation_cases + holdout_cases,
                holdout_report,
                dataset_sha256=self.DATASET_SHA,
                validation_calibration_path="scan.json",
                validation_calibration_sha256="d" * 64,
                source_report_path="holdout.json",
                source_report_sha256="e" * 64,
                generated_at="2026-08-19T00:01:00Z",
            )

    def test_split_selection_isolated_and_rejects_empty_split(self):
        validation = self._cases("validation")
        holdout = self._cases("holdout")
        cases = validation + holdout
        self.assertEqual(_select_cases_by_split(cases, "validation"), validation)
        self.assertEqual(_select_cases_by_split(cases, "holdout"), holdout)
        self.assertEqual(_select_cases_by_split(cases, "all"), cases)
        with self.assertRaises(ValueError):
            _select_cases_by_split(validation, "holdout")

    def test_cli_writes_atomic_json_and_markdown(self):
        cases, report, _ = self._passing_validation()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset_path = root / "dataset.jsonl"
            dataset_path.write_text(
                "".join(
                    json.dumps(case.to_dict(), ensure_ascii=False) + "\n"
                    for case in cases
                ),
                encoding="utf-8",
            )
            report["metadata"]["dataset_sha256"] = text_file_sha256(dataset_path)
            report_path = root / "raw.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            json_output = root / "scan.json"
            markdown_output = root / "scan.md"

            result = threshold_main(
                [
                    "scan",
                    "--dataset",
                    str(dataset_path),
                    "--validation-report",
                    str(report_path),
                    "--output-json",
                    str(json_output),
                    "--output-markdown",
                    str(markdown_output),
                ]
            )

            self.assertEqual(result, 0)
            self.assertEqual(load_json_object(json_output)["phase"], "validation")
            markdown = markdown_output.read_text(encoding="utf-8")
            self.assertIn("## Candidate Scan", markdown)
            self.assertEqual(
                calibration_to_json(load_json_object(json_output))[-1], "\n"
            )
            self.assertFalse(any(root.glob("*.tmp")))

    def test_markdown_has_no_trailing_whitespace(self):
        _, _, calibration = self._passing_validation()
        markdown = calibration_to_markdown(calibration)
        self.assertFalse(any(line.endswith(" ") for line in markdown.splitlines()))


if __name__ == "__main__":
    unittest.main()
