"""Regression gates for comparing evaluation reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Mapping

from evaluation.models import EvaluationReport


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
            if not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
                raise ValueError(f"回归阈值必须是非负有限数字: {name}")

    @staticmethod
    def _metrics(report: EvaluationReport | Mapping[str, float | None]):
        return report.metrics if isinstance(report, EvaluationReport) else report

    def evaluate(
        self,
        baseline: EvaluationReport | Mapping[str, float | None],
        current: EvaluationReport | Mapping[str, float | None],
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
                    RegressionFailure(name, baseline_value, current_value, "当前值不是有限数字")
                )
                continue
            if minimum is not None and (current_value is None or current_value < minimum):
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
