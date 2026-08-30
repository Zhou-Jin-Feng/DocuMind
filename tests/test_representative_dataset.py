import json
import tempfile
import unittest
from pathlib import Path

from evaluation.data_source_normalization import canonical_json_bytes
from evaluation.representative_dataset import (
    CATEGORIES,
    EXPECTED_DOCUMENTS,
    EXPECTED_EXPLORATION,
    EXPECTED_GOLD_CANDIDATES,
    EXPECTED_TOPICS,
    RepresentativeDatasetError,
    _privacy_findings,
    build_representative_dataset,
    finalize_representative_dataset,
    load_design,
    validate_representative_dataset,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = REPO_ROOT / "evaluation" / "representative_data" / "design.json"
CONTRACT_ROOT = REPO_ROOT / "evaluation" / "representative_data" / "contracts"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_bytes(
        b"".join(canonical_json_bytes(record) + b"\n" for record in records)
    )


class RepresentativeDesignTests(unittest.TestCase):
    def test_design_is_explicit_complete_and_balanced(self):
        design = load_design(DESIGN_PATH)

        self.assertEqual(len(design["topics"]), EXPECTED_TOPICS)
        self.assertEqual(
            {topic["id"] for topic in design["topics"]},
            {f"T{number:02d}" for number in range(1, 26)},
        )
        self.assertEqual(
            {topic["format_shape"] for topic in design["topics"]},
            {
                "table_extract",
                "yaml_config",
                "json_log",
                "ocr_extract",
                "mixed_zh_en",
            },
        )
        self.assertEqual(
            len(
                {
                    topic[state]["control_id"]
                    for topic in design["topics"]
                    for state in ("active", "draft", "superseded")
                }
            ),
            EXPECTED_DOCUMENTS,
        )

    def test_design_rejects_unknown_fields_and_non_contiguous_topics(self):
        design = json.loads(DESIGN_PATH.read_text(encoding="utf-8"))
        mutations = []

        unknown_field = json.loads(json.dumps(design))
        unknown_field["topics"][0]["unexpected"] = True
        mutations.append(unknown_field)

        missing_topic = json.loads(json.dumps(design))
        missing_topic["topics"][-1]["id"] = "T26"
        mutations.append(missing_topic)

        with tempfile.TemporaryDirectory() as temp_dir:
            for index, mutation in enumerate(mutations):
                with self.subTest(index=index):
                    path = Path(temp_dir) / f"design-{index}.json"
                    path.write_text(
                        json.dumps(mutation, ensure_ascii=False), encoding="utf-8"
                    )
                    with self.assertRaises(RepresentativeDatasetError):
                        load_design(path)

    def test_privacy_scan_detects_credentials_and_contact_values(self):
        findings = _privacy_findings(
            [
                ("credential", "api_key=abcdefghijklmnopqrstuv"),
                ("phone", "联系 13800138000"),
                ("email", "owner@example.com"),
            ]
        )

        self.assertEqual(
            {finding["type"] for finding in findings},
            {"secret_assignment", "phone", "email"},
        )


class RepresentativeBuildTests(unittest.TestCase):
    def test_build_is_deterministic_and_passes_pre_review_gate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "first"
            second = root / "second"

            first_evidence = build_representative_dataset(DESIGN_PATH, first)
            second_evidence = build_representative_dataset(DESIGN_PATH, second)
            first_validation = validate_representative_dataset(first, CONTRACT_ROOT)
            second_validation = validate_representative_dataset(second, CONTRACT_ROOT)

            self.assertTrue(first_validation["ok"], first_validation["errors"])
            self.assertTrue(second_validation["ok"], second_validation["errors"])
            self.assertEqual(
                first_evidence["snapshot"]["fingerprints"],
                second_evidence["snapshot"]["fingerprints"],
            )
            self.assertEqual(
                first_evidence["snapshot"]["review_packets"],
                second_evidence["snapshot"]["review_packets"],
            )
            self.assertEqual(
                first_validation["counts"]["documents"], EXPECTED_DOCUMENTS
            )
            self.assertEqual(
                first_validation["counts"]["exploration_questions"],
                EXPECTED_EXPLORATION,
            )
            self.assertEqual(
                first_validation["counts"]["gold_candidates"],
                EXPECTED_GOLD_CANDIDATES,
            )
            self.assertGreaterEqual(
                first_validation["shape"]["median_chunks_per_document"], 3
            )
            self.assertEqual(
                set(first_validation["shape"]["gold_category_counts"]),
                set(CATEGORIES),
            )
            self.assertEqual(
                first_validation["shape"]["gold_no_answer_by_split"],
                {"holdout": 13, "validation": 13},
            )
            self.assertFalse((first / "gold_dataset.jsonl").exists())
            self.assertEqual(
                (first / "review_batch_1.md")
                .read_text(encoding="utf-8")
                .count("\n## "),
                50,
            )
            self.assertEqual(
                (first / "review_batch_2.md")
                .read_text(encoding="utf-8")
                .count("\n## "),
                50,
            )

    def test_validator_rejects_cross_document_qrel_even_with_valid_ids(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "dataset"
            build_representative_dataset(DESIGN_PATH, output)
            candidates_path = output / "gold_candidates.jsonl"
            candidates = load_jsonl(candidates_path)
            chunks = load_jsonl(output / "chunks.jsonl")
            target = next(record for record in candidates if record["candidate_qrels"])
            qrel = target["candidate_qrels"][0]
            foreign_chunk = next(
                chunk for chunk in chunks if chunk["document_id"] != qrel["document_id"]
            )
            qrel["chunk_id"] = foreign_chunk["id"]
            write_jsonl(candidates_path, candidates)

            validation = validate_representative_dataset(output, CONTRACT_ROOT)

            self.assertFalse(validation["ok"])
            self.assertTrue(
                any(
                    "qrel document/chunk mismatch" in error
                    for error in validation["errors"]
                )
            )

    def test_replace_refuses_unowned_nonempty_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "unowned"
            output.mkdir()
            (output / "keep.txt").write_text("user-owned", encoding="utf-8")

            with self.assertRaises(RepresentativeDatasetError):
                build_representative_dataset(DESIGN_PATH, output, replace=True)

            self.assertEqual(
                (output / "keep.txt").read_text(encoding="utf-8"), "user-owned"
            )

    def test_finalize_requires_complete_review_and_applies_grade_override(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "dataset"
            build_representative_dataset(DESIGN_PATH, output)
            candidates = load_jsonl(output / "gold_candidates.jsonl")
            decisions = []
            modified_id = "REP-T13-09"
            for candidate in candidates:
                decision = {
                    "schema_version": "p2-representative-review-decision-v1",
                    "candidate_id": candidate["id"],
                    "decision": "approve",
                    "reviewer": "user",
                    "reviewed_at": "2026-08-30T00:00:00+08:00",
                    "overrides": None,
                    "notes": "人工确认通过",
                }
                if candidate["id"] == modified_id:
                    qrel = next(
                        qrel
                        for qrel in candidate["candidate_qrels"]
                        if qrel["evidence_control_id"].endswith("-OLD")
                    )
                    decision["decision"] = "modify"
                    decision["overrides"] = {
                        "qrel_grade_updates": [
                            {
                                "document_id": qrel["document_id"],
                                "chunk_id": qrel["chunk_id"],
                                "from_grade": qrel["relevance_grade"],
                                "to_grade": 3,
                            }
                        ]
                    }
                    decision["notes"] = (
                        "superseded qrel 与问题直接相关；grade 由 2 改为 3"
                    )
                decisions.append(decision)
            write_jsonl(output / "review_decisions.jsonl", decisions)

            result = finalize_representative_dataset(output, CONTRACT_ROOT)
            self.assertTrue(result["validation"]["ok"], result["validation"]["errors"])
            self.assertEqual(result["snapshot"]["status"], "gold_confirmed")
            self.assertEqual(result["snapshot"]["counts"]["gold_dataset"], 100)
            self.assertEqual(result["snapshot"]["human_review"]["approved"], 99)
            self.assertEqual(result["snapshot"]["human_review"]["modified"], 1)
            gold = load_jsonl(output / "gold_dataset.jsonl")
            reviewed = next(record for record in gold if record["id"] == modified_id)
            old_qrel = next(
                qrel
                for qrel in reviewed["qrels"]
                if qrel["evidence_control_id"].endswith("-OLD")
            )
            self.assertEqual(old_qrel["relevance_grade"], 3)
            self.assertTrue(
                all(record["label_provenance"] == "human_review" for record in gold)
            )
            with self.assertRaises(RepresentativeDatasetError):
                finalize_representative_dataset(output, CONTRACT_ROOT)


if __name__ == "__main__":
    unittest.main()
