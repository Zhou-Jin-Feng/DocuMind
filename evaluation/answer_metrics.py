"""Deterministic aggregation for answer quality case results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from statistics import fmean
from typing import Any

from evaluation.answer_models import (
    ANSWER_EVALUATION_SCHEMA_VERSION,
    JUDGE_SCORE_FIELDS,
    AnswerCaseEvaluation,
    AnswerEvaluationReport,
)


def aggregate_answer_evaluations(
    case_results: Sequence[AnswerCaseEvaluation],
    *,
    dataset_name: str,
    metadata: Mapping[str, Any],
    generated_at: str | None = None,
) -> AnswerEvaluationReport:
    """Aggregate only eligible cases and expose every metric denominator."""

    if isinstance(case_results, (str, bytes)) or not isinstance(case_results, Sequence):
        raise TypeError("case_results 必须是 AnswerCaseEvaluation 列表")
    results = tuple(case_results)
    if not results:
        raise ValueError("case_results 不能为空")
    if any(not isinstance(result, AnswerCaseEvaluation) for result in results):
        raise TypeError("case_results 只能包含 AnswerCaseEvaluation")

    successful = [result for result in results if result.status == "success"]
    refusal_values = [
        float(result.refusal_correct)
        for result in successful
        if result.refusal_correct is not None
    ]
    judge_results = [
        result.judge_result
        for result in successful
        if result.should_answer
        and result.generated_answer is not None
        and result.generated_answer.outcome == "answered"
        and result.judge_result is not None
    ]

    metrics: dict[str, float | None] = {
        "successful_case_rate": len(successful) / len(results),
        "refusal_accuracy": fmean(refusal_values) if refusal_values else None,
    }
    metric_case_counts = {
        "successful_case_rate": len(results),
        "refusal_accuracy": len(refusal_values),
    }
    for field_name in JUDGE_SCORE_FIELDS:
        values = [getattr(result, field_name) for result in judge_results]
        metrics[field_name] = fmean(values) if values else None
        metric_case_counts[field_name] = len(values)

    timestamp = generated_at or datetime.now(timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    return AnswerEvaluationReport(
        schema_version=ANSWER_EVALUATION_SCHEMA_VERSION,
        dataset_name=dataset_name,
        generated_at=timestamp,
        case_results=results,
        metadata=metadata,
        metrics=metrics,
        metric_case_counts=metric_case_counts,
    )
