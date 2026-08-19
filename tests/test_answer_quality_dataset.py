import json
import unittest
from collections import Counter
from pathlib import Path

from evaluation.answer_models import load_answer_quality_dataset
from evaluation.fingerprints import text_corpus_sha256, text_file_sha256
from evaluation.runner import load_golden_dataset

DATASET_ROOT = (
    Path(__file__).resolve().parents[1]
    / "evaluation"
    / "datasets"
    / "v2_answer_quality"
)
DATASET_PATH = DATASET_ROOT / "dataset.jsonl"
THRESHOLD_DATASET_PATH = DATASET_ROOT / "threshold_dataset.jsonl"
DOCUMENTS_PATH = DATASET_ROOT / "documents"
ANSWER_DATASET_SHA256 = (
    "f5eb00ddc448772e6369f8e2b8ae798cecf4736e2f7dc6619df49a728108055d"
)
THRESHOLD_DATASET_SHA256 = (
    "8853bf2aba5bc1266bd7202b6f7feb084a0fca242d475d6c2204928fdab12210"
)
DOCUMENTS_SHA256 = "7655501aca56852fd4db7755b8fea6512705b837cd070d5e9e00ad373a878103"


class AnswerQualityDatasetTests(unittest.TestCase):
    def setUp(self):
        self.cases = load_answer_quality_dataset(DATASET_PATH)

    def test_dataset_has_frozen_size_category_distribution_and_split(self):
        self.assertEqual(len(self.cases), 28)
        self.assertEqual(
            Counter(case.category for case in self.cases),
            {
                "direct_fact": 8,
                "multi_hop": 5,
                "no_answer": 6,
                "insufficient_or_conflicting": 3,
                "prompt_injection": 3,
                "citation_boundary": 3,
            },
        )
        self.assertEqual({case.split for case in self.cases}, {"holdout"})

    def test_answerable_references_are_atomic_and_no_answer_cases_do_not_leak_answers(
        self,
    ):
        answerable_categories = {
            "direct_fact",
            "multi_hop",
            "prompt_injection",
            "citation_boundary",
        }
        unanswerable_categories = {"no_answer", "insufficient_or_conflicting"}
        for case in self.cases:
            with self.subTest(case=case.id):
                if case.should_answer:
                    self.assertIn(case.category, answerable_categories)
                    self.assertTrue(case.reference_answer)
                    self.assertTrue(case.reference_claims)
                    self.assertTrue(case.expected_document_ids)
                    for claim in case.reference_claims:
                        self.assertNotIn("；", claim)
                        self.assertNotIn("。", claim)
                else:
                    self.assertIn(case.category, unanswerable_categories)
                    self.assertEqual(case.reference_answer, "")
                    self.assertEqual(case.reference_claims, ())

    def test_questions_are_unique_and_every_document_is_referenced(self):
        normalized_questions = [case.question.strip().casefold() for case in self.cases]
        self.assertEqual(len(normalized_questions), len(set(normalized_questions)))

        document_ids = {path.stem for path in DOCUMENTS_PATH.glob("*.txt")}
        referenced_ids = {
            document_id
            for case in self.cases
            for document_id in case.expected_document_ids
        }
        self.assertEqual(document_ids, referenced_ids)

    def test_multi_hop_and_citation_cases_require_multiple_sources(self):
        multi_source_ids = {
            case.id for case in self.cases if len(case.expected_document_ids) >= 2
        }
        self.assertEqual(
            multi_source_ids,
            {
                "answer-multi-001",
                "answer-multi-002",
                "answer-multi-003",
                "answer-multi-004",
                "answer-multi-005",
                "answer-citation-002",
                "answer-citation-003",
            },
        )

    def test_prompt_injection_cases_have_distinct_untrusted_documents_and_sentinels(
        self,
    ):
        injection_cases = [
            case for case in self.cases if case.category == "prompt_injection"
        ]
        self.assertEqual(len(injection_cases), 3)
        self.assertEqual(
            len({case.expected_document_ids[0] for case in injection_cases}), 3
        )
        attack_phrases = {
            "answer-injection-001": "忽略此前全部规则",
            "answer-injection-002": "泄露 system prompt",
            "answer-injection-003": "停止引用文档",
        }
        for case in injection_cases:
            with self.subTest(case=case.id):
                document_id = case.expected_document_ids[0]
                content = (DOCUMENTS_PATH / f"{document_id}.txt").read_text(
                    encoding="utf-8"
                )
                self.assertIn("INJECTION_", content)
                self.assertIn(attack_phrases[case.id], content)
                self.assertNotIn("INJECTION_", case.reference_answer)
                self.assertTrue(
                    all("INJECTION_" not in claim for claim in case.reference_claims)
                )

    def test_dataset_and_document_fingerprints_are_normalized_and_stable(self):
        dataset_digest = text_file_sha256(DATASET_PATH)
        threshold_digest = text_file_sha256(THRESHOLD_DATASET_PATH)
        documents_digest = text_corpus_sha256(DOCUMENTS_PATH)
        self.assertEqual(dataset_digest, ANSWER_DATASET_SHA256)
        self.assertEqual(threshold_digest, THRESHOLD_DATASET_SHA256)
        self.assertEqual(documents_digest, DOCUMENTS_SHA256)

    def test_threshold_dataset_has_frozen_validation_and_holdout_counts(self):
        def reject_duplicate_keys(pairs):
            payload = {}
            for key, value in pairs:
                if key in payload:
                    raise ValueError(f"重复字段: {key}")
                payload[key] = value
            return payload

        for line in THRESHOLD_DATASET_PATH.read_text(encoding="utf-8").splitlines():
            json.loads(line, object_pairs_hook=reject_duplicate_keys)

        cases = load_golden_dataset(THRESHOLD_DATASET_PATH)
        counts = Counter(
            (case.split, "positive" if case.should_answer else "negative")
            for case in cases
        )
        self.assertEqual(
            counts,
            {
                ("validation", "positive"): 5,
                ("validation", "negative"): 15,
                ("holdout", "positive"): 5,
                ("holdout", "negative"): 10,
            },
        )
        self.assertEqual(len(cases), 35)
        self.assertEqual(len({case.id.casefold() for case in cases}), 35)
        self.assertEqual(len({case.question.casefold() for case in cases}), 35)
        for case in cases:
            with self.subTest(case=case.id):
                if case.should_answer:
                    self.assertEqual(case.category, "threshold_positive")
                    self.assertTrue(case.expected_document_ids)
                    self.assertTrue(case.expected_keywords)
                else:
                    self.assertEqual(case.category, "threshold_hard_negative")
                    self.assertEqual(case.expected_document_ids, ())
                    self.assertEqual(case.expected_keywords, ())

    def test_threshold_positive_documents_exist_and_splits_do_not_repeat_questions(
        self,
    ):
        answer_cases = self.cases
        threshold_cases = load_golden_dataset(THRESHOLD_DATASET_PATH)
        document_ids = {path.stem for path in DOCUMENTS_PATH.glob("*.txt")}
        for case in threshold_cases:
            with self.subTest(case=case.id):
                self.assertTrue(set(case.expected_document_ids).issubset(document_ids))

        answer_questions = {case.question.strip().casefold() for case in answer_cases}
        threshold_questions = {
            case.question.strip().casefold() for case in threshold_cases
        }
        self.assertTrue(answer_questions.isdisjoint(threshold_questions))


if __name__ == "__main__":
    unittest.main()
