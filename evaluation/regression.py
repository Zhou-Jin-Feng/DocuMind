"""Regression gates for comparing evaluation reports."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path
from typing import Any, Mapping

from evaluation.models import EvaluationReport


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError(f"评估报告 JSON 包含重复字段: {key}")
        payload[key] = value
    return payload


COMPARABLE_METADATA_KEYS = (
    "embedding_provider",
    "embedding_model",
    "embedding_dimension",
    "chunk_size",
    "chunk_overlap",
    "case_top_k_values",
    "score_threshold",
    "lexical_score_threshold",
    "dense_weight",
    "lexical_weight",
    "rrf_k",
    "candidate_multiplier",
    "retrieval_mode",
)


@dataclass(frozen=True)
class EvaluationSnapshot:
    """Validated report fields required by the regression gate."""

    dataset_name: str
    top_k: int
    case_count: int
    metadata: Mapping[str, Any]
    metrics: Mapping[str, float | None]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvaluationSnapshot":
        if not isinstance(payload, Mapping):
            raise TypeError("评估报告必须是 JSON 对象")
        dataset_name = payload.get("dataset_name")
        if not isinstance(dataset_name, str) or not dataset_name.strip():
            raise ValueError("评估报告缺少 dataset_name")
        top_k = payload.get("top_k")
        case_count = payload.get("case_count")
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k <= 0:
            raise ValueError("评估报告 top_k 必须是正整数")
        if (
            not isinstance(case_count, int)
            or isinstance(case_count, bool)
            or case_count <= 0
        ):
            raise ValueError("评估报告 case_count 必须是正整数")

        raw_metadata = payload.get("metadata", {})
        raw_metrics = payload.get("metrics")
        if not isinstance(raw_metadata, Mapping):
            raise TypeError("评估报告 metadata 必须是 JSON 对象")
        if not isinstance(raw_metrics, Mapping):
            raise TypeError("评估报告 metrics 必须是 JSON 对象")

        metrics: dict[str, float | None] = {}
        for name, value in raw_metrics.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("评估指标名称不能为空")
            if value is None:
                metrics[name] = None
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"评估指标必须是数字或 null: {name}")
            numeric_value = float(value)
            if not isfinite(numeric_value):
                raise ValueError(f"评估指标必须是有限数字: {name}")
            metrics[name] = numeric_value

        return cls(
            dataset_name=dataset_name.strip(),
            top_k=top_k,
            case_count=case_count,
            metadata=dict(raw_metadata),
            metrics=metrics,
        )


def load_evaluation_snapshot(path: str | Path) -> EvaluationSnapshot:
    """Load and validate a JSON evaluation report or aggregate baseline."""

    report_path = Path(path)
    if not report_path.is_file():
        raise FileNotFoundError(f"评估报告不存在: {report_path}")
    try:
        payload = json.loads(
            report_path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"评估报告不是有效 JSON: {report_path}") from exc
    return EvaluationSnapshot.from_dict(payload)


def report_compatibility_issues(
    baseline: EvaluationSnapshot,
    current: EvaluationSnapshot,
) -> tuple[str, ...]:
    """Reject comparisons that do not use the same evaluation inputs."""

    issues: list[str] = []
    for label, baseline_value, current_value in (
        ("dataset_name", baseline.dataset_name, current.dataset_name),
        ("top_k", baseline.top_k, current.top_k),
        ("case_count", baseline.case_count, current.case_count),
    ):
        if baseline_value != current_value:
            issues.append(f"{label} 不一致: {baseline_value!r} != {current_value!r}")

    for key in ("dataset_sha256", "documents_sha256"):
        baseline_value = baseline.metadata.get(key)
        current_value = current.metadata.get(key)
        if not baseline_value or not current_value:
            issues.append(f"缺少可比性字段: metadata.{key}")
        elif baseline_value != current_value:
            issues.append(f"metadata.{key} 不一致")
    for key in COMPARABLE_METADATA_KEYS:
        baseline_has_key = key in baseline.metadata
        current_has_key = key in current.metadata
        if not baseline_has_key and not current_has_key:
            continue
        if not baseline_has_key or not current_has_key:
            issues.append(f"metadata.{key} 仅存在于一份报告")
        elif baseline.metadata[key] != current.metadata[key]:
            issues.append(f"metadata.{key} 不一致")
    return tuple(issues)


@dataclass(frozen=True)
class RegressionFailure:
    metric: str
    baseline: float | None
    current: float | None
    reason: str


@dataclass(frozen=True)
class RegressionResult:
    passed: bool
    checked_metrics: tuple[str, ...]
    failures: tuple[RegressionFailure, ...] = field(default_factory=tuple)

    def assert_passed(self) -> None:
        if not self.passed:
            details = "; ".join(
                f"{failure.metric}: {failure.reason}" for failure in self.failures
            )
            raise AssertionError(f"RAG 评估回归门禁失败: {details}")


@dataclass(frozen=True)
class RegressionGate:
    """Fail when a metric drops beyond its allowed absolute tolerance."""

    allowed_drops: Mapping[str, float] = field(default_factory=dict)
    minimums: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, value in {**self.allowed_drops, **self.minimums}.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("回归指标名称不能为空")
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value < 0
            ):
                raise ValueError(f"回归阈值必须是非负有限数字: {name}")

    @staticmethod
    def _metrics(
        report: EvaluationReport | EvaluationSnapshot | Mapping[str, float | None],
    ):
        if isinstance(report, (EvaluationReport, EvaluationSnapshot)):
            return report.metrics
        return report

    def evaluate(
        self,
        baseline: EvaluationReport | EvaluationSnapshot | Mapping[str, float | None],
        current: EvaluationReport | EvaluationSnapshot | Mapping[str, float | None],
    ) -> RegressionResult:
        baseline_metrics = self._metrics(baseline)
        current_metrics = self._metrics(current)
        names = tuple(sorted(set(self.allowed_drops) | set(self.minimums)))
        failures: list[RegressionFailure] = []

        for name in names:
            baseline_value = baseline_metrics.get(name)
            current_value = current_metrics.get(name)
            minimum = self.minimums.get(name)
            allowed_drop = self.allowed_drops.get(name, 0.0)

            if current_value is not None and not isfinite(current_value):
                failures.append(
                    RegressionFailure(
                        name, baseline_value, current_value, "当前值不是有限数字"
                    )
                )
                continue
            if minimum is not None and (
                current_value is None or current_value < minimum
            ):
                failures.append(
                    RegressionFailure(
                        name,
                        baseline_value,
                        current_value,
                        f"低于最低阈值 {minimum:.4f}",
                    )
                )
                continue
            if baseline_value is None:
                continue
            if current_value is None or current_value < baseline_value - allowed_drop:
                failures.append(
                    RegressionFailure(
                        name,
                        baseline_value,
                        current_value,
                        f"下降超过允许值 {allowed_drop:.4f}",
                    )
                )

        return RegressionResult(
            passed=not failures,
            checked_metrics=names,
            failures=tuple(failures),
        )
