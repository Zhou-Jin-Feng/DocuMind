"""Strict comparison of the four v1.7 retrieval enhancement modes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from evaluation.regression import (
    COMPARABLE_METADATA_KEYS,
    EvaluationSnapshot,
    report_compatibility_issues,
)

ENHANCEMENT_MODES = ("baseline", "rewrite", "rerank", "rewrite-rerank")
COMPARISON_METRICS = (
    "recall_at_k",
    "precision_at_k",
    "mrr_at_k",
    "top_k_hit_rate",
    "no_answer_retrieval_accuracy",
    "successful_case_rate",
    "average_duration_ms",
    "p50_duration_ms",
    "p95_duration_ms",
    "maximum_duration_ms",
)
COMMON_METADATA_KEYS = (
    *COMPARABLE_METADATA_KEYS,
    "dataset_sha256",
    "documents_sha256",
)


@dataclass(frozen=True)
class EvaluationComparison:
    """Serializable quality and latency matrix for compatible reports."""

    common_metadata: Mapping[str, Any]
    metrics_by_mode: Mapping[str, Mapping[str, float | None]]
    deltas_from_baseline: Mapping[str, Mapping[str, float | None]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "modes": list(ENHANCEMENT_MODES),
            "common_metadata": dict(self.common_metadata),
            "metrics_by_mode": {
                mode: dict(metrics) for mode, metrics in self.metrics_by_mode.items()
            },
            "deltas_from_baseline": {
                mode: dict(metrics)
                for mode, metrics in self.deltas_from_baseline.items()
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n"

    def to_markdown(self) -> str:
        lines = [
            "# v1.7.1 Retrieval Enhancement Comparison",
            "",
            "## Common Configuration",
            "",
            "| Setting | Value |",
            "|---|---|",
        ]
        for name, value in self.common_metadata.items():
            formatted = json.dumps(value, ensure_ascii=False)
            lines.append(f"| `{name}` | `{formatted}` |")
        lines.extend(
            [
                "",
                "## Quality And Latency",
                "",
                "| Mode | Recall@K | Precision@K | MRR@K | Hit Rate | No-answer | Success | Avg ms | P50 ms | P95 ms | Max ms |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        labels = {
            "recall_at_k": "recall_at_k",
            "precision_at_k": "precision_at_k",
            "mrr_at_k": "mrr_at_k",
            "top_k_hit_rate": "top_k_hit_rate",
            "no_answer_retrieval_accuracy": "no_answer_retrieval_accuracy",
            "successful_case_rate": "successful_case_rate",
            "average_duration_ms": "average_duration_ms",
            "p50_duration_ms": "p50_duration_ms",
            "p95_duration_ms": "p95_duration_ms",
            "maximum_duration_ms": "maximum_duration_ms",
        }
        for mode in ENHANCEMENT_MODES:
            metrics = self.metrics_by_mode[mode]

            def formatted(name: str) -> str:
                value = metrics.get(labels[name])
                return "N/A" if value is None else f"{value:.4f}"

            lines.append(
                f"| `{mode}` | {formatted('recall_at_k')} | "
                f"{formatted('precision_at_k')} | "
                f"{formatted('mrr_at_k')} | "
                f"{formatted('top_k_hit_rate')} | "
                f"{formatted('no_answer_retrieval_accuracy')} | "
                f"{formatted('successful_case_rate')} | "
                f"{formatted('average_duration_ms')} | "
                f"{formatted('p50_duration_ms')} | "
                f"{formatted('p95_duration_ms')} | "
                f"{formatted('maximum_duration_ms')} |"
            )
        lines.extend(
            [
                "",
                "All deltas in the JSON artifact use `mode - baseline`; quality and "
                "latency are intentionally not collapsed into one score.",
            ]
        )
        return "\n".join(lines) + "\n"


def build_evaluation_comparison(
    snapshots: Mapping[str, EvaluationSnapshot],
) -> EvaluationComparison:
    """Validate four like-for-like reports and produce their metric matrix."""

    if set(snapshots) != set(ENHANCEMENT_MODES):
        missing = sorted(set(ENHANCEMENT_MODES) - set(snapshots))
        unknown = sorted(set(snapshots) - set(ENHANCEMENT_MODES))
        raise ValueError(f"评估模式不完整: missing={missing}, unknown={unknown}")

    baseline = snapshots["baseline"]
    issues: list[str] = []
    for mode in ENHANCEMENT_MODES:
        snapshot = snapshots[mode]
        actual_mode = snapshot.metadata.get("enhancement_mode")
        if actual_mode != mode:
            issues.append(f"{mode}: metadata.enhancement_mode 不一致: {actual_mode!r}")
        if mode != "baseline":
            issues.extend(
                f"{mode}: {issue}"
                for issue in report_compatibility_issues(baseline, snapshot)
            )
        for key in COMMON_METADATA_KEYS:
            baseline_value = baseline.metadata.get(key)
            current_value = snapshot.metadata.get(key)
            if key not in baseline.metadata or key not in snapshot.metadata:
                issues.append(f"{mode}: 缺少共同配置 metadata.{key}")
            elif current_value != baseline_value:
                issues.append(f"{mode}: metadata.{key} 不一致")
    if issues:
        raise ValueError("评估报告不可直接比较: " + "; ".join(dict.fromkeys(issues)))

    metrics_by_mode = {
        mode: {name: snapshots[mode].metrics.get(name) for name in COMPARISON_METRICS}
        for mode in ENHANCEMENT_MODES
    }
    baseline_metrics = metrics_by_mode["baseline"]
    deltas: dict[str, dict[str, float | None]] = {}
    for mode in ENHANCEMENT_MODES:
        mode_deltas: dict[str, float | None] = {}
        for name in COMPARISON_METRICS:
            baseline_value = baseline_metrics[name]
            current_value = metrics_by_mode[mode][name]
            mode_deltas[name] = (
                None
                if baseline_value is None or current_value is None
                else current_value - baseline_value
            )
        deltas[mode] = mode_deltas

    return EvaluationComparison(
        common_metadata={key: baseline.metadata[key] for key in COMMON_METADATA_KEYS},
        metrics_by_mode=metrics_by_mode,
        deltas_from_baseline=deltas,
    )
