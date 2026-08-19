"""Deterministic score-threshold calibration from raw Dense retrieval reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import floor, isfinite, nextafter
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence

from evaluation.metrics import recall_at_k, reciprocal_rank_at_k
from evaluation.models import GoldenCase

THRESHOLD_CALIBRATION_SCHEMA_VERSION = 1
SELECTION_POLICY = "largest-passing-adjacent-midpoint-v1"
COMPATIBLE_CONFIGURATION_KEYS = (
    "embedding_provider",
    "embedding_model",
    "embedding_dimension",
    "chunk_size",
    "chunk_overlap",
    "case_top_k_values",
    "retrieval_mode",
    "enhancement_mode",
    "distance_metric",
    "dataset_sha256",
    "documents_sha256",
)


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError(f"JSON 包含重复字段: {key}")
        payload[key] = value
    return payload


def load_json_object(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        payload = json.loads(
            source.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"JSON 不允许非有限数: {value}")
            ),
        )
    except UnicodeDecodeError as exc:
        raise ValueError(f"JSON 不是有效 UTF-8: {source}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 格式无效: {source}") from exc
    if not isinstance(payload, dict):
        raise TypeError("JSON 顶层必须是对象")
    return payload


@dataclass(frozen=True)
class ThresholdConstraints:
    """Pre-declared quality constraints for validation and holdout."""

    max_recall_drop: float = 0.02
    min_no_answer_accuracy: float = 0.90
    min_successful_case_rate: float = 1.0

    def __post_init__(self) -> None:
        for name, value in (
            ("max_recall_drop", self.max_recall_drop),
            ("min_no_answer_accuracy", self.min_no_answer_accuracy),
            ("min_successful_case_rate", self.min_successful_case_rate),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} 必须是数字")
            if not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} 必须是 0 到 1 的有限数")

    def to_dict(self) -> dict[str, float]:
        return {
            "max_recall_drop": float(self.max_recall_drop),
            "min_no_answer_accuracy": float(self.min_no_answer_accuracy),
            "min_successful_case_rate": float(self.min_successful_case_rate),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ThresholdConstraints":
        if not isinstance(payload, Mapping):
            raise TypeError("constraints 必须是对象")
        expected = {
            "max_recall_drop",
            "min_no_answer_accuracy",
            "min_successful_case_rate",
        }
        if set(payload) != expected:
            raise ValueError("constraints 字段不完整或包含未知字段")
        return cls(**{name: payload[name] for name in expected})


@dataclass(frozen=True)
class _Observation:
    case: GoldenCase
    retrieved_document_ids: tuple[str, ...]
    retrieved_distances: tuple[float, ...]


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = floor(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _distribution(values: Sequence[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "minimum": None,
            "mean": None,
            "p50": None,
            "p95": None,
            "maximum": None,
        }
    numeric = [float(value) for value in values]
    return {
        "count": len(numeric),
        "minimum": min(numeric),
        "mean": mean(numeric),
        "p50": _percentile(numeric, 0.5),
        "p95": _percentile(numeric, 0.95),
        "maximum": max(numeric),
    }


def _configuration(metadata: Mapping[str, Any]) -> dict[str, Any]:
    missing = [key for key in COMPATIBLE_CONFIGURATION_KEYS if key not in metadata]
    if missing:
        raise ValueError(f"检索报告缺少配置字段: {', '.join(missing)}")
    configuration = {key: metadata[key] for key in COMPATIBLE_CONFIGURATION_KEYS}
    if configuration["retrieval_mode"] != "dense":
        raise ValueError("阈值校准只接受 Dense 检索报告")
    if configuration["enhancement_mode"] != "baseline":
        raise ValueError("阈值校准不接受检索增强报告")
    if str(configuration["distance_metric"]).upper() != "L2":
        raise ValueError("阈值校准只接受 L2 distance")
    return configuration


def _observations_from_report(
    cases: Sequence[GoldenCase],
    report: Mapping[str, Any],
    *,
    expected_split: str,
    dataset_sha256: str,
) -> tuple[list[_Observation], dict[str, Any]]:
    selected_cases = [case for case in cases if case.split == expected_split]
    if not selected_cases:
        raise ValueError(f"数据集没有 {expected_split} 案例")
    if any(
        bool(case.expected_document_ids) != case.should_answer
        for case in selected_cases
    ):
        raise ValueError("阈值数据集的 should_answer 与 expected_document_ids 不一致")
    raw_metadata = report.get("metadata")
    raw_results = report.get("cases")
    if not isinstance(raw_metadata, Mapping):
        raise TypeError("检索报告 metadata 必须是对象")
    if not isinstance(raw_results, list):
        raise TypeError("检索报告 cases 必须是列表")
    if raw_metadata.get("score_threshold") is not None:
        raise ValueError("阈值校准输入必须是无阈值原始报告")
    if raw_metadata.get("evaluation_split") != expected_split:
        raise ValueError(f"检索报告不是 {expected_split} split")
    if raw_metadata.get("dataset_sha256") != dataset_sha256:
        raise ValueError("检索报告与阈值数据集指纹不一致")
    configuration = _configuration(raw_metadata)
    if report.get("case_count") != len(selected_cases):
        raise ValueError("检索报告 case_count 与 split 案例数不一致")

    expected_by_id = {case.id: case for case in selected_cases}
    results_by_id: dict[str, Mapping[str, Any]] = {}
    for raw_result in raw_results:
        if not isinstance(raw_result, Mapping):
            raise TypeError("检索报告案例必须是对象")
        case_id = raw_result.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("检索报告案例缺少 case_id")
        if case_id in results_by_id:
            raise ValueError(f"检索报告包含重复案例: {case_id}")
        results_by_id[case_id] = raw_result
    if set(results_by_id) != set(expected_by_id):
        raise ValueError("检索报告案例集合与目标 split 不一致")

    observations: list[_Observation] = []
    for case in selected_cases:
        raw_result = results_by_id[case.id]
        if raw_result.get("status") != "success":
            raise ValueError(f"检索报告案例未成功: {case.id}")
        if raw_result.get("question") != case.question:
            raise ValueError(f"检索报告问题与数据集不一致: {case.id}")
        if raw_result.get("top_k") != case.top_k:
            raise ValueError(f"检索报告 Top-K 与数据集不一致: {case.id}")
        raw_ids = raw_result.get("retrieved_document_ids")
        raw_distances = raw_result.get("retrieved_distances")
        if not isinstance(raw_ids, list) or not all(
            isinstance(value, str) and value for value in raw_ids
        ):
            raise ValueError(f"检索报告文档 ID 无效: {case.id}")
        if not isinstance(raw_distances, list) or len(raw_distances) != len(raw_ids):
            raise ValueError(f"检索报告 distance 与文档数量不一致: {case.id}")
        distances: list[float] = []
        for value in raw_distances:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"检索报告 distance 必须是数字: {case.id}")
            distance = float(value)
            if not isfinite(distance) or distance < 0:
                raise ValueError(f"检索报告 distance 必须是非负有限数: {case.id}")
            distances.append(distance)
        if distances != sorted(distances):
            raise ValueError(f"Dense L2 distance 未按升序排列: {case.id}")
        observations.append(_Observation(case, tuple(raw_ids), tuple(distances)))
    return observations, configuration


def adjacent_midpoint_candidates(values: Sequence[float]) -> tuple[float, ...]:
    """Return only representable midpoints between adjacent observed distances."""

    unique: list[float] = []
    for value in sorted(values):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("distance 必须是数字")
        numeric = float(value)
        if not isfinite(numeric) or numeric < 0:
            raise ValueError("distance 必须是非负有限数")
        if not unique or numeric != unique[-1]:
            unique.append(numeric)
    candidates: list[float] = []
    for lower, upper in zip(unique, unique[1:]):
        midpoint = lower + (upper - lower) / 2
        if midpoint <= lower:
            midpoint = nextafter(lower, upper)
        if lower < midpoint < upper:
            candidates.append(midpoint)
    return tuple(candidates)


def _evaluate(
    observations: Sequence[_Observation], threshold: float | None
) -> dict[str, float | int | None]:
    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    no_answer_results: list[float] = []
    false_rejections = 0
    answerable_count = 0
    retrieved_counts: list[int] = []
    for observation in observations:
        if threshold is None:
            retained_ids = list(observation.retrieved_document_ids)
        else:
            retained_ids = [
                document_id
                for document_id, distance in zip(
                    observation.retrieved_document_ids,
                    observation.retrieved_distances,
                )
                if distance <= threshold
            ]
        retained_ids = retained_ids[: observation.case.top_k]
        retrieved_counts.append(len(retained_ids))
        if observation.case.should_answer:
            answerable_count += 1
            if not retained_ids:
                false_rejections += 1
            recall = recall_at_k(
                observation.case.expected_document_ids,
                retained_ids,
                observation.case.top_k,
            )
            reciprocal_rank = reciprocal_rank_at_k(
                observation.case.expected_document_ids,
                retained_ids,
                observation.case.top_k,
            )
            if recall is not None:
                recalls.append(recall)
            if reciprocal_rank is not None:
                reciprocal_ranks.append(reciprocal_rank)
        else:
            no_answer_results.append(float(not retained_ids))
    return {
        "answerable_recall_at_k": mean(recalls) if recalls else None,
        "answerable_mrr_at_k": mean(reciprocal_ranks) if reciprocal_ranks else None,
        "no_answer_retrieval_accuracy": (
            mean(no_answer_results) if no_answer_results else None
        ),
        "false_rejection_rate": (
            false_rejections / answerable_count if answerable_count else None
        ),
        "successful_case_rate": 1.0,
        "average_retrieved_count": mean(retrieved_counts),
        "answerable_case_count": answerable_count,
        "no_answer_case_count": len(no_answer_results),
    }


def _passes_constraints(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    constraints: ThresholdConstraints,
) -> bool:
    baseline_recall = baseline["answerable_recall_at_k"]
    candidate_recall = candidate["answerable_recall_at_k"]
    no_answer_accuracy = candidate["no_answer_retrieval_accuracy"]
    successful_case_rate = candidate["successful_case_rate"]
    if any(
        value is None
        for value in (
            baseline_recall,
            candidate_recall,
            no_answer_accuracy,
            successful_case_rate,
        )
    ):
        return False
    epsilon = 1e-12
    return bool(
        baseline_recall - candidate_recall <= constraints.max_recall_drop + epsilon
        and no_answer_accuracy + epsilon >= constraints.min_no_answer_accuracy
        and successful_case_rate + epsilon >= constraints.min_successful_case_rate
    )


def _distance_evidence(
    observations: Sequence[_Observation],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw: list[dict[str, Any]] = []
    grouped: dict[str, dict[str, list[float]]] = {
        "answerable": {"top1": [], "top_k": []},
        "no_answer": {"top1": [], "top_k": []},
    }
    for observation in observations:
        group = "answerable" if observation.case.should_answer else "no_answer"
        distances = list(observation.retrieved_distances)
        raw.append(
            {
                "case_id": observation.case.id,
                "answerable": observation.case.should_answer,
                "retrieved_document_ids": list(observation.retrieved_document_ids),
                "retrieved_distances": distances,
            }
        )
        if distances:
            grouped[group]["top1"].append(distances[0])
            grouped[group]["top_k"].extend(distances)
    summaries = {
        group: {
            "top1": _distribution(values["top1"]),
            "all_top_k": _distribution(values["top_k"]),
        }
        for group, values in grouped.items()
    }
    return raw, summaries


def build_validation_calibration(
    cases: Sequence[GoldenCase],
    report: Mapping[str, Any],
    *,
    dataset_sha256: str,
    source_report_path: str,
    source_report_sha256: str,
    generated_at: str,
    constraints: ThresholdConstraints | None = None,
) -> dict[str, Any]:
    constraints = constraints or ThresholdConstraints()
    observations, configuration = _observations_from_report(
        cases,
        report,
        expected_split="validation",
        dataset_sha256=dataset_sha256,
    )
    baseline = _evaluate(observations, None)
    all_distances = [
        distance
        for observation in observations
        for distance in observation.retrieved_distances
    ]
    candidate_rows: list[dict[str, Any]] = []
    for threshold in adjacent_midpoint_candidates(all_distances):
        metrics = _evaluate(observations, threshold)
        candidate_rows.append(
            {
                "threshold": threshold,
                "metrics": metrics,
                "passes_constraints": _passes_constraints(
                    baseline, metrics, constraints
                ),
            }
        )
    passing = [row for row in candidate_rows if row["passes_constraints"]]
    selected_threshold = max(row["threshold"] for row in passing) if passing else None
    raw_distances, summaries = _distance_evidence(observations)
    return {
        "schema_version": THRESHOLD_CALIBRATION_SCHEMA_VERSION,
        "phase": "validation",
        "generated_at": generated_at,
        "source": {
            "report_path": source_report_path,
            "report_sha256": source_report_sha256,
            "dataset_sha256": dataset_sha256,
        },
        "configuration": configuration,
        "constraints": constraints.to_dict(),
        "selection_policy": SELECTION_POLICY,
        "selection_rationale": (
            "Only adjacent observed-distance midpoints are eligible; among rows "
            "meeting every constraint, choose the largest threshold to preserve "
            "the broadest answerable recall margin."
        ),
        "baseline_metrics": baseline,
        "distance_observations": raw_distances,
        "distance_summaries": summaries,
        "candidate_count": len(candidate_rows),
        "candidates": candidate_rows,
        "selected_threshold": selected_threshold,
        "validation_passed": selected_threshold is not None,
        "holdout_status": (
            "eligible_not_run"
            if selected_threshold is not None
            else "not_run_no_validation_candidate"
        ),
        "enable_reference_threshold": (
            None if selected_threshold is not None else False
        ),
        "code_default_remains_none": True,
        "decision": (
            "candidate_selected" if selected_threshold is not None else "do_not_enable"
        ),
    }


def _validated_validation_calibration(
    calibration: Mapping[str, Any],
) -> tuple[float, ThresholdConstraints, Mapping[str, Any]]:
    if calibration.get("schema_version") != THRESHOLD_CALIBRATION_SCHEMA_VERSION:
        raise ValueError("不支持的阈值校准 schema_version")
    if calibration.get("phase") != "validation":
        raise ValueError("最终决策需要 validation 校准报告")
    if calibration.get("selection_policy") != SELECTION_POLICY:
        raise ValueError("阈值选择策略不兼容")
    constraints = ThresholdConstraints.from_dict(calibration.get("constraints", {}))
    selected = calibration.get("selected_threshold")
    if isinstance(selected, bool) or not isinstance(selected, (int, float)):
        raise ValueError("validation 报告没有冻结候选阈值")
    selected = float(selected)
    candidates = calibration.get("candidates")
    if not isinstance(candidates, list):
        raise TypeError("validation candidates 必须是列表")
    matches = [
        row
        for row in candidates
        if isinstance(row, Mapping)
        and row.get("threshold") == selected
        and row.get("passes_constraints") is True
    ]
    if len(matches) != 1:
        raise ValueError("冻结阈值不是唯一的通过候选")
    passing_thresholds = [
        float(row["threshold"])
        for row in candidates
        if isinstance(row, Mapping) and row.get("passes_constraints") is True
    ]
    if not passing_thresholds or selected != max(passing_thresholds):
        raise ValueError("冻结阈值不符合最大通过候选选择规则")
    configuration = calibration.get("configuration")
    if not isinstance(configuration, Mapping):
        raise TypeError("validation configuration 必须是对象")
    return selected, constraints, configuration


def build_holdout_decision(
    validation_calibration: Mapping[str, Any],
    cases: Sequence[GoldenCase],
    holdout_report: Mapping[str, Any],
    *,
    dataset_sha256: str,
    validation_calibration_path: str,
    validation_calibration_sha256: str,
    source_report_path: str,
    source_report_sha256: str,
    generated_at: str,
) -> dict[str, Any]:
    selected, constraints, validation_configuration = _validated_validation_calibration(
        validation_calibration
    )
    observations, holdout_configuration = _observations_from_report(
        cases,
        holdout_report,
        expected_split="holdout",
        dataset_sha256=dataset_sha256,
    )
    if dict(validation_configuration) != holdout_configuration:
        raise ValueError("validation 与 holdout 检索配置不兼容")
    baseline = _evaluate(observations, None)
    selected_metrics = _evaluate(observations, selected)
    passed = _passes_constraints(baseline, selected_metrics, constraints)
    raw_distances, summaries = _distance_evidence(observations)
    return {
        "schema_version": THRESHOLD_CALIBRATION_SCHEMA_VERSION,
        "phase": "holdout_decision",
        "generated_at": generated_at,
        "validation_calibration": {
            "path": validation_calibration_path,
            "sha256": validation_calibration_sha256,
            "selected_threshold": selected,
        },
        "source": {
            "report_path": source_report_path,
            "report_sha256": source_report_sha256,
            "dataset_sha256": dataset_sha256,
        },
        "configuration": holdout_configuration,
        "constraints": constraints.to_dict(),
        "selection_policy": SELECTION_POLICY,
        "selected_threshold": selected,
        "baseline_metrics": baseline,
        "selected_threshold_metrics": selected_metrics,
        "distance_observations": raw_distances,
        "distance_summaries": summaries,
        "holdout_passed": passed,
        "enable_reference_threshold": passed,
        "code_default_remains_none": True,
        "decision": "enable_reference_threshold" if passed else "do_not_enable",
        "decision_reason": (
            "The frozen validation threshold satisfied all holdout constraints."
            if passed
            else "The frozen validation threshold failed at least one holdout constraint."
        ),
    }


def calibration_to_json(payload: Mapping[str, Any]) -> str:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )


def _format(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return format(value, ".12g")
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def _metric_rows(metrics: Mapping[str, Any]) -> list[str]:
    return [f"| `{name}` | {_format(value)} |" for name, value in metrics.items()]


def calibration_to_markdown(payload: Mapping[str, Any]) -> str:
    phase = payload.get("phase")
    lines = ["# Retrieval Threshold Calibration", "", f"- Phase: `{phase}`"]
    lines.extend(
        [
            f"- Generated at: `{_format(payload.get('generated_at'))}`",
            f"- Selection policy: `{_format(payload.get('selection_policy'))}`",
            f"- Selected threshold: `{_format(payload.get('selected_threshold'))}`",
            f"- Decision: `{_format(payload.get('decision'))}`",
            f"- Holdout status: `{_format(payload.get('holdout_status'))}`",
            "",
            "## Configuration",
            "",
            "| Field | Value |",
            "|---|---|",
        ]
    )
    for name, value in payload.get("configuration", {}).items():
        lines.append(f"| `{name}` | {_format(value)} |")
    lines.extend(
        [
            "",
            "## Constraints",
            "",
            "| Constraint | Value |",
            "|---|---:|",
        ]
    )
    for name, value in payload.get("constraints", {}).items():
        lines.append(f"| `{name}` | {_format(value)} |")
    lines.extend(
        [
            "",
            "## No-threshold Baseline",
            "",
            "| Metric | Value |",
            "|---|---:|",
            *_metric_rows(payload.get("baseline_metrics", {})),
        ]
    )
    if phase == "validation":
        lines.extend(
            [
                "",
                "## Candidate Scan",
                "",
                "| Threshold | Recall@K | MRR@K | No-answer accuracy | False rejection | Success | Pass |",
                "|---:|---:|---:|---:|---:|---:|---|",
            ]
        )
        for row in payload.get("candidates", []):
            metrics = row["metrics"]
            lines.append(
                f"| {_format(row['threshold'])} | "
                f"{_format(metrics['answerable_recall_at_k'])} | "
                f"{_format(metrics['answerable_mrr_at_k'])} | "
                f"{_format(metrics['no_answer_retrieval_accuracy'])} | "
                f"{_format(metrics['false_rejection_rate'])} | "
                f"{_format(metrics['successful_case_rate'])} | "
                f"{_format(row['passes_constraints'])} |"
            )
    else:
        lines.extend(
            [
                "",
                "## Frozen-threshold Holdout",
                "",
                "| Metric | Value |",
                "|---|---:|",
                *_metric_rows(payload.get("selected_threshold_metrics", {})),
                "",
                f"Reference deployment enabled: **{_format(payload.get('enable_reference_threshold'))}**",
                "",
                _format(payload.get("decision_reason")),
            ]
        )
    lines.extend(["", "## Distance Distributions", ""])
    for group, summaries in payload.get("distance_summaries", {}).items():
        lines.extend(
            [
                f"### {group}",
                "",
                "| Scope | Count | Min | Mean | P50 | P95 | Max |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for scope, summary in summaries.items():
            lines.append(
                f"| `{scope}` | {summary['count']} | "
                f"{_format(summary['minimum'])} | {_format(summary['mean'])} | "
                f"{_format(summary['p50'])} | {_format(summary['p95'])} | "
                f"{_format(summary['maximum'])} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
