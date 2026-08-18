import json
import tempfile
import unittest
from pathlib import Path

from evaluation.answer_adapters import (
    AnswerGenerator,
    AnswerJudge,
    FakeAnswerGenerator,
    FakeAnswerJudge,
)
from evaluation.answer_metrics import aggregate_answer_evaluations
from evaluation.answer_models import (
    REFUSAL_TEXT,
    AnswerCaseEvaluation,
    AnswerQualityCase,
    GeneratedAnswer,
    JudgeResult,
    load_answer_quality_dataset,
)
from evaluation.fingerprints import text_sha256
from evaluation.models import RetrievedDocument


class AnswerEvaluationTests(unittest.TestCase):
    @staticmethod
    def _case_payload(**overrides):
        payload = {
            "id": "answer-direct-001",
            "question": "active 索引在什么时候切换？",
            "expected_document_ids": ["lifecycle-operations"],
            "should_answer": True,
            "reference_answer": "新索引成功后才切换 active。",
            "reference_claims": ["新索引成功后才切换 active"],
            "category": "direct_fact",
            "split": "holdout",
            "top_k": 3,
        }
        payload.update(overrides)
        return payload

    @staticmethod
    def _case(**overrides):
        return AnswerQualityCase.from_dict(
            AnswerEvaluationTests._case_payload(**overrides)
        )

    @staticmethod
    def _judge(**overrides):
        payload = {
            "faithfulness": 0.9,
            "citation_correctness": 0.8,
            "citation_completeness": 0.7,
            "answer_relevance": 1.0,
            "unsupported_claims": [],
            "invalid_citations": [],
            "reason": "回答由文档支持。",
        }
        payload.update(overrides)
        return JudgeResult.from_dict(payload)

    @staticmethod
    def _metadata():
        return {
            "git_commit": None,
            "dirty": True,
            "dataset_sha256": "a" * 64,
            "documents_sha256": "b" * 64,
            "embedding_provider": "evaluation-fake",
            "embedding_model": "sha256-token-hash-v1",
            "embedding_dimension": 64,
            "chunk_size": 500,
            "chunk_overlap": 50,
            "retrieval_mode": "dense",
            "top_k": 3,
            "score_threshold": None,
            "generator_provider": "fake",
            "generator_model": "fixture-v1",
            "generator_temperature": 0.0,
            "generator_max_tokens": 256,
            "generator_prompt_sha256": "c" * 64,
            "judge_provider": "fake",
            "judge_model": "fixture-v1",
            "judge_temperature": 0.0,
            "judge_max_tokens": 256,
            "judge_prompt_sha256": "d" * 64,
            "refusal_text_sha256": text_sha256(REFUSAL_TEXT),
            "citation_parser_version": "fixture-v1",
        }

    def test_answer_quality_case_enforces_answerability_contract(self):
        case = self._case(category=" Direct_Fact ", split=" HOLDOUT ")
        self.assertEqual(case.category, "direct_fact")
        self.assertEqual(case.split, "holdout")

        with self.assertRaisesRegex(ValueError, "expected_document_ids"):
            self._case(expected_document_ids=[])
        with self.assertRaisesRegex(ValueError, "reference_answer"):
            self._case(reference_answer="")
        with self.assertRaisesRegex(ValueError, "reference_claims"):
            self._case(reference_claims=[])
        with self.assertRaisesRegex(ValueError, "必须为空"):
            self._case(should_answer=False)
        with self.assertRaisesRegex(ValueError, "unknown"):
            AnswerQualityCase.from_dict({**self._case_payload(), "unknown": True})
        with self.assertRaisesRegex(ValueError, "missing"):
            payload = self._case_payload()
            del payload["top_k"]
            AnswerQualityCase.from_dict(payload)
        with self.assertRaisesRegex(ValueError, "train/validation/holdout"):
            self._case(split="all")
        with self.assertRaisesRegex(ValueError, "正整数"):
            self._case(top_k=True)

    def test_answer_dataset_loader_is_strict_and_validates_document_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            documents = root / "documents"
            documents.mkdir()
            (documents / "lifecycle-operations.txt").write_text(
                "active 索引在新索引成功后切换。", encoding="utf-8"
            )
            no_answer = self._case_payload(
                id="answer-none-001",
                question="负责人是谁？",
                expected_document_ids=[],
                should_answer=False,
                reference_answer="",
                reference_claims=[],
                category="no_answer",
            )
            dataset = root / "dataset.jsonl"
            content = (
                json.dumps(self._case_payload(), ensure_ascii=False)
                + "\r\n\r\n"
                + json.dumps(no_answer, ensure_ascii=False)
                + "\r\n"
            )
            dataset.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))

            cases = load_answer_quality_dataset(dataset)

            self.assertEqual(
                [case.id for case in cases],
                [
                    "answer-direct-001",
                    "answer-none-001",
                ],
            )

            bad_payload = self._case_payload(expected_document_ids=["missing"])
            dataset.write_text(
                json.dumps(bad_payload, ensure_ascii=False), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "未知文档 ID"):
                load_answer_quality_dataset(dataset)

    def test_answer_dataset_loader_rejects_duplicate_keys_ids_and_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            documents = root / "documents"
            documents.mkdir()
            (documents / "lifecycle-operations.txt").write_text(
                "fixture", encoding="utf-8"
            )
            dataset = root / "dataset.jsonl"
            valid = json.dumps(self._case_payload(), ensure_ascii=False)
            duplicate_key = valid.replace(
                '"id": "answer-direct-001",',
                '"id": "answer-direct-001", "id": "duplicate",',
                1,
            )
            dataset.write_text(duplicate_key, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "重复字段"):
                load_answer_quality_dataset(dataset)

            dataset.write_text(f"{valid}\n{valid}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "id 重复"):
                load_answer_quality_dataset(dataset)

            dataset.write_bytes(b"\xff\xfe\x00")
            with self.assertRaisesRegex(ValueError, "UTF-8"):
                load_answer_quality_dataset(dataset)

    def test_generated_answer_uses_exact_refusal_and_fixed_outcome_order(self):
        document = RetrievedDocument("doc", content="evidence", rank=1)

        no_context = GeneratedAnswer.from_generation("", [])
        refused = GeneratedAnswer.from_generation(f"  {REFUSAL_TEXT}\n", [document])
        answered = GeneratedAnswer.from_generation(
            f"{REFUSAL_TEXT} 但我根据常识补充一点。", [document]
        )

        self.assertEqual(no_context.outcome, "no_context")
        self.assertEqual(refused.outcome, "refused")
        self.assertEqual(answered.outcome, "answered")
        with self.assertRaisesRegex(ValueError, "空文本"):
            GeneratedAnswer.from_generation("  ", [document])
        with self.assertRaisesRegex(ValueError, "不应调用生成器"):
            GeneratedAnswer.from_generation("unexpected", [])

    def test_judge_result_accepts_only_exact_strict_json(self):
        valid = json.dumps(self._judge().to_dict(), ensure_ascii=False)
        parsed = JudgeResult.from_json(valid)
        self.assertEqual(parsed.faithfulness, 0.9)

        invalid_payloads = {
            "duplicate": valid.replace(
                '"faithfulness": 0.9,',
                '"faithfulness": 0.9, "faithfulness": 1.0,',
                1,
            ),
            "extra": valid[:-1] + ', "extra": true}',
            "missing": json.dumps(
                {
                    key: value
                    for key, value in self._judge().to_dict().items()
                    if key != "reason"
                }
            ),
            "boolean": valid.replace('"faithfulness": 0.9', '"faithfulness": true'),
            "nan": valid.replace('"faithfulness": 0.9', '"faithfulness": NaN'),
            "infinity": valid.replace(
                '"faithfulness": 0.9', '"faithfulness": Infinity'
            ),
            "markdown": f"```json\n{valid}\n```",
            "prefix": f"Judge result: {valid}",
            "array": "[]",
        }
        for name, raw in invalid_payloads.items():
            with self.subTest(name=name):
                with self.assertRaises((TypeError, ValueError)):
                    JudgeResult.from_json(raw)

        with self.assertRaisesRegex(ValueError, "0 到 1"):
            self._judge(faithfulness=1.01)

    def test_fake_generator_and_judge_implement_shared_protocols_offline(self):
        case = self._case()
        document = RetrievedDocument("lifecycle-operations", content="evidence")
        judge_result = self._judge()
        generator = FakeAnswerGenerator({case.id: "回答 [文档1]"})
        judge = FakeAnswerJudge({case.id: judge_result})

        self.assertIsInstance(generator, AnswerGenerator)
        self.assertIsInstance(judge, AnswerJudge)
        answer_text = generator.generate(case, [document])
        generated = GeneratedAnswer.from_generation(
            answer_text, [document], citations=[1]
        )
        self.assertIs(judge.judge(case, generated), judge_result)
        self.assertEqual(generator.calls, (case.id,))
        self.assertEqual(judge.calls, (case.id,))

        with self.assertRaisesRegex(KeyError, "缺少案例映射"):
            generator.generate(self._case(id="missing"), [document])

    def test_aggregate_metrics_exclude_errors_and_non_judged_cases(self):
        document = RetrievedDocument("lifecycle-operations", content="evidence", rank=1)
        answered_case = self._case(id="answered")
        refused_case = self._case(
            id="refused",
            should_answer=False,
            reference_answer="",
            reference_claims=[],
        )
        missed_case = self._case(id="missed")
        error_case = self._case(id="error")
        results = (
            AnswerCaseEvaluation.success(
                answered_case,
                GeneratedAnswer.from_generation(
                    "新索引成功后才切换 [文档1]",
                    [document],
                    citations=[1],
                ),
                judge_result=self._judge(),
            ),
            AnswerCaseEvaluation.success(
                refused_case,
                GeneratedAnswer.from_generation(REFUSAL_TEXT, [document]),
            ),
            AnswerCaseEvaluation.success(
                missed_case,
                GeneratedAnswer.no_context(retrieval_duration_ms=1.5),
            ),
            AnswerCaseEvaluation.error(
                error_case,
                error_stage="generation",
                error_type="TimeoutError",
                generated_answer=GeneratedAnswer.error(
                    retrieved_documents=[document], retrieval_duration_ms=2.0
                ),
            ),
        )

        report = aggregate_answer_evaluations(
            results,
            dataset_name="fixture",
            metadata=self._metadata(),
            generated_at="2026-08-19T00:00:00Z",
        )

        self.assertEqual(report.metrics["successful_case_rate"], 0.75)
        self.assertAlmostEqual(report.metrics["refusal_accuracy"], 2 / 3)
        self.assertEqual(report.metric_case_counts["refusal_accuracy"], 3)
        for field_name in (
            "faithfulness",
            "citation_correctness",
            "citation_completeness",
            "answer_relevance",
        ):
            self.assertEqual(report.metric_case_counts[field_name], 1)
        payload = json.loads(report.to_json())
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["case_count"], 4)
        self.assertEqual(payload["cases"][3]["error_stage"], "generation")
        self.assertIsNone(payload["cases"][3]["judge_result"])

    def test_report_requires_complete_reproducibility_metadata(self):
        case = self._case(should_answer=False, reference_answer="", reference_claims=[])
        result = AnswerCaseEvaluation.success(
            case,
            GeneratedAnswer.from_generation(
                REFUSAL_TEXT, [RetrievedDocument("lifecycle-operations")]
            ),
        )
        metadata = self._metadata()
        del metadata["judge_prompt_sha256"]

        with self.assertRaisesRegex(ValueError, "metadata 缺少"):
            aggregate_answer_evaluations(
                [result], dataset_name="fixture", metadata=metadata
            )


if __name__ == "__main__":
    unittest.main()
