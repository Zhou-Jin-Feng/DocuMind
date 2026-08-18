"""Provider-neutral protocols and deterministic fakes for answer evaluation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from evaluation.answer_models import (
    AnswerQualityCase,
    GeneratedAnswer,
    JudgeResult,
)
from evaluation.models import RetrievedDocument


@runtime_checkable
class AnswerGenerator(Protocol):
    """Generate one candidate answer from a case and retrieved evidence."""

    def generate(
        self,
        case: AnswerQualityCase,
        retrieved_documents: Sequence[RetrievedDocument],
    ) -> str: ...


@runtime_checkable
class AnswerJudge(Protocol):
    """Score one validated generated answer."""

    def judge(
        self,
        case: AnswerQualityCase,
        generated_answer: GeneratedAnswer,
    ) -> JudgeResult: ...


class FakeAnswerGenerator:
    """Case-ID mapping implementation that never initializes a provider client."""

    def __init__(self, answers_by_case_id: Mapping[str, str]):
        self._answers = self._normalize_mapping(answers_by_case_id)
        self._calls: list[str] = []

    @staticmethod
    def _normalize_id(value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("案例 ID 必须是非空字符串")
        return value.strip().casefold()

    @classmethod
    def _normalize_mapping(cls, values: Mapping[str, str]) -> dict[str, str]:
        if not isinstance(values, Mapping):
            raise TypeError("answers_by_case_id 必须是映射")
        normalized: dict[str, str] = {}
        for case_id, answer in values.items():
            key = cls._normalize_id(case_id)
            if key in normalized:
                raise ValueError(f"Fake Generator 案例 ID 重复: {case_id}")
            if not isinstance(answer, str):
                raise TypeError("Fake Generator 回答必须是字符串")
            normalized[key] = answer
        return normalized

    @property
    def calls(self) -> tuple[str, ...]:
        return tuple(self._calls)

    def generate(
        self,
        case: AnswerQualityCase,
        retrieved_documents: Sequence[RetrievedDocument],
    ) -> str:
        del retrieved_documents
        key = self._normalize_id(case.id)
        self._calls.append(case.id)
        try:
            return self._answers[key]
        except KeyError as exc:
            raise KeyError(f"Fake Generator 缺少案例映射: {case.id}") from exc


class FakeAnswerJudge:
    """Case-ID mapping implementation of the same protocol as a real judge."""

    def __init__(self, results_by_case_id: Mapping[str, JudgeResult]):
        if not isinstance(results_by_case_id, Mapping):
            raise TypeError("results_by_case_id 必须是映射")
        normalized: dict[str, JudgeResult] = {}
        for case_id, result in results_by_case_id.items():
            key = FakeAnswerGenerator._normalize_id(case_id)
            if key in normalized:
                raise ValueError(f"Fake Judge 案例 ID 重复: {case_id}")
            if not isinstance(result, JudgeResult):
                raise TypeError("Fake Judge 结果必须是 JudgeResult")
            normalized[key] = result
        self._results = normalized
        self._calls: list[str] = []

    @property
    def calls(self) -> tuple[str, ...]:
        return tuple(self._calls)

    def judge(
        self,
        case: AnswerQualityCase,
        generated_answer: GeneratedAnswer,
    ) -> JudgeResult:
        del generated_answer
        key = FakeAnswerGenerator._normalize_id(case.id)
        self._calls.append(case.id)
        try:
            return self._results[key]
        except KeyError as exc:
            raise KeyError(f"Fake Judge 缺少案例映射: {case.id}") from exc
