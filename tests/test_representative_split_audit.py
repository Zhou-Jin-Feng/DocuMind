import json
import shutil
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from evaluation.representative_split_audit import (
    DEFAULT_AUDIT_JSON,
    DEFAULT_AUDIT_MARKDOWN,
    DEFAULT_FREEZE,
    SplitAuditError,
    audit_representative_splits,
    freeze_representative_splits,
    validate_frozen_representative_splits,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = REPO_ROOT / "evaluation" / "datasets" / "p2_retrieval_v2"
CONTRACT_ROOT = REPO_ROOT / "evaluation" / "representative_data" / "contracts"


class RepresentativeSplitAuditTests(unittest.TestCase):
    def _copy_dataset(self, temporary_root: Path) -> Path:
        target = temporary_root / "dataset"
        shutil.copytree(DATASET_ROOT, target)
        return target

    def test_ds05_contracts_are_valid_and_strict(self):
        for filename in (
            "split-freeze-v1.schema.json",
            "split-audit-v1.schema.json",
        ):
            schema = json.loads((CONTRACT_ROOT / filename).read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)

    def test_audit_and_freeze_are_deterministic_and_isolated(self):
        with tempfile.TemporaryDirectory() as temporary:
            dataset = self._copy_dataset(Path(temporary))
            first_audit = audit_representative_splits(dataset, CONTRACT_ROOT)
            self.assertEqual(first_audit["status"], "passed")
            self.assertEqual(first_audit["splits"]["validation"]["count"], 50)
            self.assertEqual(first_audit["splits"]["holdout"]["count"], 50)
            self.assertTrue(
                all(not values for values in first_audit["overlap_checks"].values())
            )
            self.assertEqual(first_audit["near_duplicate_questions"], [])

            first_root = Path(temporary) / "first"
            first_root.mkdir()
            first = freeze_representative_splits(
                dataset,
                CONTRACT_ROOT,
                freeze_path=first_root / DEFAULT_FREEZE.name,
                audit_json_path=first_root / DEFAULT_AUDIT_JSON.name,
                audit_markdown_path=first_root / DEFAULT_AUDIT_MARKDOWN.name,
            )
            second_root = Path(temporary) / "second"
            second_root.mkdir()
            second = freeze_representative_splits(
                dataset,
                CONTRACT_ROOT,
                freeze_path=second_root / DEFAULT_FREEZE.name,
                audit_json_path=second_root / DEFAULT_AUDIT_JSON.name,
                audit_markdown_path=second_root / DEFAULT_AUDIT_MARKDOWN.name,
            )
            self.assertEqual(first, second)
            validation = validate_frozen_representative_splits(
                dataset,
                CONTRACT_ROOT,
                freeze_path=first_root / DEFAULT_FREEZE.name,
                audit_json_path=first_root / DEFAULT_AUDIT_JSON.name,
                audit_markdown_path=first_root / DEFAULT_AUDIT_MARKDOWN.name,
            )
            self.assertTrue(validation["ok"], validation["errors"])

    def test_freeze_refuses_existing_outputs_without_replace(self):
        with tempfile.TemporaryDirectory() as temporary:
            dataset = self._copy_dataset(Path(temporary))
            output = Path(temporary) / "artifacts"
            output.mkdir()
            freeze_path = output / "split_freeze.json"
            audit_json = output / "audit.json"
            audit_markdown = output / "audit.md"
            freeze_path.write_text("keep", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                freeze_representative_splits(
                    dataset,
                    CONTRACT_ROOT,
                    freeze_path=freeze_path,
                    audit_json_path=audit_json,
                    audit_markdown_path=audit_markdown,
                )
            self.assertEqual(freeze_path.read_text(encoding="utf-8"), "keep")
            self.assertFalse(audit_json.exists())
            self.assertFalse(audit_markdown.exists())

    def test_validation_detects_gold_mutation_after_freeze(self):
        with tempfile.TemporaryDirectory() as temporary:
            dataset = self._copy_dataset(Path(temporary))
            output = Path(temporary) / "artifacts"
            freeze_representative_splits(
                dataset,
                CONTRACT_ROOT,
                freeze_path=output / "split_freeze.json",
                audit_json_path=output / "audit.json",
                audit_markdown_path=output / "audit.md",
            )
            gold_path = dataset / "gold_dataset.jsonl"
            gold_path.write_bytes(gold_path.read_bytes() + b"\n")
            with self.assertRaises(SplitAuditError):
                validate_frozen_representative_splits(
                    dataset,
                    CONTRACT_ROOT,
                    freeze_path=output / "split_freeze.json",
                    audit_json_path=output / "audit.json",
                    audit_markdown_path=output / "audit.md",
                )


if __name__ == "__main__":
    unittest.main()
