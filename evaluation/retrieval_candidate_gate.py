"""Strict P2 gate for deciding whether a retrieval candidate may go online."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from math import floor, isclose, isfinite
from pathlib import Path
from typing import Any, Mapping, Sequence

from evaluation.fingerprints import text_file_sha256
from evaluation.regression import EvaluationSnapshot

REPORT_KINDS = ("dense", "bm25", "hybrid", "rerank")
CANDIDATE_KINDS = REPORT_KINDS[1:]
QUALITY_METRICS = (
    "recall_at_k",
    "mrr_at_k",
    "no_answer_retrieval_accuracy",
)
COMMON_METADATA_KEYS = (
    "document_count",
    "chunk_count",
    "chunk_size",
    "chunk_overlap",
    "case_count",
    "case_top_k_values",
    "dataset_sha256",
    "documents_sha256",
    "evaluation_split",
)
VECTOR_METADATA_KEYS = (
    "embedding_provider",
    "embedding_model",
    "embedding_dimension",
    "score_threshold",
)
HYBRID_METADATA_KEYS = (
    "lexical_score_threshold",
    "dense_weight",
    "lexical_weight",
    "rrf_k",
    "candidate_multiplier",
)


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError(f"retrieval candidate report has duplicate field: {key}")
        payload[key] = value
    return payload


def _finite_non_negative(value: float, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    if not isfinite(float(value)) or float(value) < 0:
        raise ValueError(f"{name} must be finite and non-negative")


@dataclass(frozen=True)
class RetrievalCandidatePolicy:
    """Frozen evidence, quality and latency requirements for P2 candidates."""

    minimum_total_cases: int = 30
    minimum_validation_cases: int = 15
    minimum_holdout_cases: int = 15
    minimum_holdout_answerable_cases: int = 5
    minimum_holdout_no_answer_cases: int = 5
    minimum_recall_gain: float = 0.02
    minimum_mrr_gain: float = 0.02
    minimum_no_answer_gain: float = 0.05
    allowed_quality_drop: float = 0.0
    minimum_successful_case_rate: float = 1.0
    maximum_p95_increase_ms: float = 750.0
    maximum_p95_multiplier: float = 2.0

    def __post_init__(self) -> None:
        for name in (
            "minimum_total_cases",
            "minimum_validation_cases",
            "minimum_holdout_cases",
            "minimum_holdout_answerable_cases",
            "minimum_holdout_no_answer_cases",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        for name in (
            "minimum_recall_gain",
            "minimum_mrr_gain",
            "minimum_no_answer_gain",
            "allowed_quality_drop",
            "minimum_successful_case_rate",
            "maximum_p95_increase_ms",
            "maximum_p95_multiplier",
        ):
            _finite_non_negative(getattr(self, name), name)
        if self.minimum_successful_case_rate > 1:
            raise ValueError("minimum_successful_case_rate cannot exceed 1")
        if self.maximum_p95_multiplier < 1:
            raise ValueError("maximum_p95_multiplier cannot be lower than 1")


@dataclass(frozen=True)
class LoadedCandidateReport:
    """Validated report plus evidence fields not retained by EvaluationSnapshot."""

    kind: str
    path: Path
    display_path: str
    source_sha256: str
    snapshot: EvaluationSnapshot
    payload: Mapping[str, Any]
    case_fingerprint: str
    validation_case_count: int
    holdout_case_count: int
    holdout_answerable_case_count: int
    holdout_no_answer_case_count: int
    holdout_metrics: Mapping[str, float | None]


@dataclass(frozen=True)
class CandidateResult:
    """Decision details for one candidate compared with Dense."""

    eligible: bool
    failures: tuple[str, ...]
    holdout_metrics: Mapping[str, float | None]
    deltas_from_dense: Mapping[str, float | None]
    p95_increase_ms: float | None
    p95_multiplier: float | None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "failures": list(self.failures),
            "holdout_metrics": dict(self.holdout_metrics),
            "deltas_from_dense": dict(self.deltas_from_dense),
            "p95_increase_ms": self.p95_increase_ms,
            "p95_multiplier": self.p95_multiplier,
            "diagnostics": dict(self.diagnostics),
        }


@dataclass(frozen=True)
class RetrievalCandidateDecision:
    """Serializable GO/NO_GO artifact for the P2 online retrieval gate."""

    policy: RetrievalCandidatePolicy
    reports: Mapping[str, LoadedCandidateReport]
    global_failures: tuple[str, ...]
    candidates: Mapping[str, CandidateResult]
    decision: str
    selected_candidate: str | None

    def to_dict(self) -> dict[str, Any]:
        baseline = self.reports["dense"]
        return {
            "schema_version": "1.0",
            "decision": self.decision,
            "selected_candidate": self.selected_candidate,
            "public_contract_action": (
                "review_selected_candidate"
                if self.decision == "GO"
                else "keep_schema_1_0_dense_v1"
            ),
            "policy": asdict(self.policy),
            "evidence": {
                "dataset_sha256": baseline.snapshot.metadata.get("dataset_sha256"),
                "documents_sha256": baseline.snapshot.metadata.get("documents_sha256"),
                "case_fingerprint": baseline.case_fingerprint,
                "total_case_count": baseline.snapshot.case_count,
                "validation_case_count": baseline.validation_case_count,
                "holdout_case_count": baseline.holdout_case_count,
                "holdout_answerable_case_count": (
                    baseline.holdout_answerable_case_count
                ),
                "holdout_no_answer_case_count": (baseline.holdout_no_answer_case_count),
                "source_reports": {
                    kind: {
                        "path": report.display_path,
                        "sha256": report.source_sha256,
                    }
                    for kind, report in self.reports.items()
                },
            },
            "global_failures": list(self.global_failures),
            "dense_holdout_metrics": dict(baseline.holdout_metrics),
            "candidates": {
                kind: result.to_dict() for kind, result in self.candidates.items()
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n"

    def to_markdown(self) -> str:
        payload = self.to_dict()
        evidence = payload["evidence"]
        lines = [
            "# P2 Retrieval Candidate Decision",
            "",
            f"Decision: **{self.decision}**",
            "",
            f"Selected candidate: `{self.selected_candidate or 'none'}`",
            "",
            f"Public contract action: `{payload['public_contract_action']}`",
            "",
            "## Evidence",
            "",
            "| Item | Value |",
            "|---|---:|",
            f"| Total cases | {evidence['total_case_count']} |",
            f"| Validation cases | {evidence['validation_case_count']} |",
            f"| Holdout cases | {evidence['holdout_case_count']} |",
            (
                "| Holdout answerable / no-answer | "
                f"{evidence['holdout_answerable_case_count']} / "
                f"{evidence['holdout_no_answer_case_count']} |"
            ),
            "",
            "## Holdout Comparison",
            "",
            "| Mode | Eligible | Recall@K | MRR@K | No-answer | P95 ms | Failures |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]

        def metric(value: Any) -> str:
            return "N/A" if value is None else f"{float(value):.4f}"

        dense_metrics = self.reports["dense"].holdout_metrics
        lines.append(
            "| `dense` | baseline | "
            f"{metric(dense_metrics.get('recall_at_k'))} | "
            f"{metric(dense_metrics.get('mrr_at_k'))} | "
            f"{metric(dense_metrics.get('no_answer_retrieval_accuracy'))} | "
            f"{metric(dense_metrics.get('p95_duration_ms'))} | 0 |"
        )
        for kind in CANDIDATE_KINDS:
            result = self.candidates[kind]
            metrics = result.holdout_metrics
            lines.append(
                f"| `{kind}` | {'yes' if result.eligible else 'no'} | "
                f"{metric(metrics.get('recall_at_k'))} | "
                f"{metric(metrics.get('mrr_at_k'))} | "
                f"{metric(metrics.get('no_answer_retrieval_accuracy'))} | "
                f"{metric(metrics.get('p95_duration_ms'))} | "
                f"{len(result.failures)} |"
            )
        lines.extend(
            [
                "",
                "## Diagnostic Signals",
                "",
                "| Mode | Answerable Top-1 | Rank improved / regressed | Changed ranks | No-answer non-empty | Holdout duration range |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        baseline_diagnostics = _candidate_diagnostics(
            self.reports["dense"], self.reports["dense"]
        )

        def diagnostic_row(kind: str, diagnostics: Mapping[str, Any]) -> str:
            top1 = diagnostics.get("candidate_answerable_top1_rate")
            top1_text = "N/A" if top1 is None else f"{float(top1):.4f}"
            improved = diagnostics.get("answerable_rank_improvements", 0)
            regressed = diagnostics.get("answerable_rank_regressions", 0)
            changed = diagnostics.get("changed_rank_case_count", 0)
            no_answer = diagnostics.get("candidate_no_answer_non_empty_rate")
            no_answer_text = "N/A" if no_answer is None else f"{float(no_answer):.4f}"
            minimum = diagnostics.get("candidate_holdout_duration_min_ms")
            maximum = diagnostics.get("candidate_holdout_duration_max_ms")
            duration_text = (
                "N/A"
                if minimum is None or maximum is None
                else f"{float(minimum):.1f} - {float(maximum):.1f}"
            )
            return (
                f"| `{kind}` | {top1_text} | {improved} / {regressed} | "
                f"{changed} | {no_answer_text} | {duration_text} |"
            )

        lines.append(diagnostic_row("dense", baseline_diagnostics))
        for kind in CANDIDATE_KINDS:
            lines.append(diagnostic_row(kind, self.candidates[kind].diagnostics))
        lines.extend(
            [
                "",
                "`Answerable Top-1` exposes the quality headroom that aggregate MRR can hide; "
                "`No-answer non-empty` is the fraction of no-answer cases that still returned "
                "candidates. The current comparison uses no rejection threshold, so the latter "
                "is not a refusal-quality score.",
            ]
        )
        if self.global_failures:
            lines.extend(["", "## Global Failures", ""])
            lines.extend(f"- {failure}" for failure in self.global_failures)
        lines.extend(["", "## Candidate Findings", ""])
        for kind in CANDIDATE_KINDS:
            result = self.candidates[kind]
            lines.append(f"### {kind}")
            lines.append("")
            if result.failures:
                lines.extend(f"- {failure}" for failure in result.failures)
            else:
                lines.append("- All policy checks passed.")
            lines.append("")
        lines.extend(
            [
                "A `GO` result authorizes review of the selected candidate; it does not "
                "change the public API automatically. A `NO_GO` result keeps Schema "
                "`1.0` and `dense-v1` unchanged.",
                "",
            ]
        )
        return "\n".join(lines)


def _safe_display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.name


def _required_text(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"candidate report case has invalid {field}")
    return value.strip()


def _case_evidence(
    payload: Mapping[str, Any], case_count: int
) -> tuple[str, int, int, int, int]:
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or len(raw_cases) != case_count:
        raise ValueError("candidate report cases do not match case_count")
    signatures: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    split_counts = {"validation": 0, "holdout": 0}
    holdout_answerable = 0
    holdout_no_answer = 0
    for raw_case in raw_cases:
        if not isinstance(raw_case, Mapping):
            raise TypeError("candidate report case must be an object")
        case_id = _required_text(raw_case, "case_id")
        if case_id in seen_ids:
            raise ValueError(f"candidate report has duplicate case_id: {case_id}")
        seen_ids.add(case_id)
        question = _required_text(raw_case, "question")
        category = _required_text(raw_case, "category")
        split = _required_text(raw_case, "split").casefold()
        top_k = raw_case.get("top_k")
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k <= 0:
            raise ValueError(f"candidate report case has invalid top_k: {case_id}")
        if split not in split_counts:
            raise ValueError(
                f"candidate evidence must use validation/holdout splits: {case_id}"
            )
        split_counts[split] += 1
        status = raw_case.get("status")
        if status not in {"success", "error"}:
            raise ValueError(f"candidate report case has invalid status: {case_id}")
        metrics = raw_case.get("metrics")
        if not isinstance(metrics, Mapping):
            raise TypeError(
                f"candidate report case metrics must be an object: {case_id}"
            )
        if split == "holdout":
            if metrics.get("no_answer_retrieval_accuracy") is None:
                holdout_answerable += 1
            else:
                holdout_no_answer += 1
        signatures.append(
            {
                "case_id": case_id,
                "question": question,
                "top_k": top_k,
                "category": category,
                "split": split,
            }
        )
    serialized = json.dumps(
        signatures, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return (
        hashlib.sha256(serialized).hexdigest(),
        split_counts["validation"],
        split_counts["holdout"],
        holdout_answerable,
        holdout_no_answer,
    )


def _mean_defined(values: Sequence[float | None]) -> float | None:
    defined = [value for value in values if value is not None]
    return sum(defined) / len(defined) if defined else None


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = floor(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _numeric_case_value(case: Mapping[str, Any], field: str) -> float | None:
    metrics = case.get("metrics")
    if not isinstance(metrics, Mapping):
        raise TypeError("candidate report case metrics must be an object")
    value = metrics.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(
            f"candidate report case metric must be numeric or null: {field}"
        )
    numeric = float(value)
    if not isfinite(numeric):
        raise ValueError(f"candidate report case metric must be finite: {field}")
    return numeric


def _assert_aggregate_matches(
    split: str,
    field: str,
    reported: Any,
    recomputed: float | None,
    *,
    absolute_tolerance: float = 1e-9,
) -> None:
    if reported is None and recomputed is None:
        return
    if isinstance(reported, bool) or not isinstance(reported, (int, float)):
        raise TypeError(
            f"candidate report {split} aggregate must be numeric or null: {field}"
        )
    if recomputed is None or not isclose(
        float(reported),
        recomputed,
        rel_tol=1e-9,
        abs_tol=absolute_tolerance,
    ):
        raise ValueError(
            f"candidate report {split} aggregate {field} is inconsistent with cases"
        )


def _validate_split_aggregates(
    payload: Mapping[str, Any], split_metrics: Mapping[str, Any]
) -> None:
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        raise TypeError("candidate report cases must be an array")
    for split in ("validation", "holdout"):
        aggregate = split_metrics.get(split)
        if not isinstance(aggregate, Mapping):
            raise ValueError(f"candidate report is missing {split} split metrics")
        cases = [
            case
            for case in raw_cases
            if isinstance(case, Mapping)
            and str(case.get("split", "")).casefold() == split
        ]
        if not cases:
            raise ValueError(f"candidate report has no {split} cases")
        for field in QUALITY_METRICS:
            if field in aggregate:
                recomputed = _mean_defined(
                    [_numeric_case_value(case, field) for case in cases]
                )
                _assert_aggregate_matches(
                    split, field, aggregate.get(field), recomputed
                )
        if "successful_case_rate" in aggregate:
            success_rate = sum(case.get("status") == "success" for case in cases) / len(
                cases
            )
            _assert_aggregate_matches(
                split,
                "successful_case_rate",
                aggregate.get("successful_case_rate"),
                success_rate,
            )
        durations: list[float] = []
        for case in cases:
            value = case.get("duration_ms")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError("candidate report case duration_ms must be numeric")
            duration = float(value)
            if not isfinite(duration) or duration < 0:
                raise ValueError(
                    "candidate report case duration_ms must be finite and non-negative"
                )
            durations.append(duration)
        if "p95_duration_ms" in aggregate:
            _assert_aggregate_matches(
                split,
                "p95_duration_ms",
                aggregate.get("p95_duration_ms"),
                _percentile(durations, 0.95),
                absolute_tolerance=5e-4,
            )


def _load_report(kind: str, path: str | Path) -> LoadedCandidateReport:
    report_path = Path(path)
    if not report_path.is_file():
        raise FileNotFoundError(f"candidate report does not exist: {report_path}")
    try:
        payload = json.loads(
            report_path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"candidate report is not valid JSON: {report_path}") from exc
    if not isinstance(payload, Mapping):
        raise TypeError("candidate report must be a JSON object")
    snapshot = EvaluationSnapshot.from_dict(payload)
    case_evidence = _case_evidence(payload, snapshot.case_count)
    split_metrics = payload.get("split_metrics")
    if not isinstance(split_metrics, Mapping):
        raise TypeError("candidate report split_metrics must be an object")
    validation_metrics = split_metrics.get("validation")
    holdout_metrics = split_metrics.get("holdout")
    if not isinstance(validation_metrics, Mapping):
        raise ValueError("candidate report is missing validation split metrics")
    if not isinstance(holdout_metrics, Mapping):
        raise ValueError("candidate report is missing holdout split metrics")
    _validate_split_aggregates(payload, split_metrics)
    if snapshot.metadata.get("case_count") != snapshot.case_count:
        raise ValueError("candidate report metadata.case_count is inconsistent")
    if case_evidence[1] + case_evidence[2] != snapshot.case_count:
        raise ValueError("candidate report split case counts are inconsistent")
    for split, metrics, actual_count in (
        ("validation", validation_metrics, case_evidence[1]),
        ("holdout", holdout_metrics, case_evidence[2]),
    ):
        metric_count = metrics.get("case_count")
        if (
            isinstance(metric_count, bool)
            or not isinstance(metric_count, (int, float))
            or float(metric_count) != float(actual_count)
        ):
            raise ValueError(
                f"candidate report {split} metric case_count is inconsistent"
            )
    parsed_holdout_metrics: dict[str, float | None] = {}
    for name, value in holdout_metrics.items():
        if value is None:
            parsed_holdout_metrics[str(name)] = None
        elif isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"holdout metric must be numeric or null: {name}")
        elif not isfinite(float(value)):
            raise ValueError(f"holdout metric must be finite: {name}")
        else:
            parsed_holdout_metrics[str(name)] = float(value)
    return LoadedCandidateReport(
        kind=kind,
        path=report_path,
        display_path=_safe_display_path(report_path),
        # Candidate reports are UTF-8 JSON artifacts; hash logical text so the
        # evidence remains stable across Windows CRLF and Linux LF checkouts.
        source_sha256=text_file_sha256(report_path),
        snapshot=snapshot,
        payload=payload,
        case_fingerprint=case_evidence[0],
        validation_case_count=case_evidence[1],
        holdout_case_count=case_evidence[2],
        holdout_answerable_case_count=case_evidence[3],
        holdout_no_answer_case_count=case_evidence[4],
        holdout_metrics=parsed_holdout_metrics,
    )


def _identity_failures(reports: Mapping[str, LoadedCandidateReport]) -> list[str]:
    failures: list[str] = []
    expected = {
        "dense": ("dense", "baseline"),
        "bm25": ("bm25", "baseline"),
        "hybrid": ("hybrid", "baseline"),
        "rerank": ("hybrid", "rerank"),
    }
    for kind, (retrieval_mode, enhancement_mode) in expected.items():
        metadata = reports[kind].snapshot.metadata
        if metadata.get("retrieval_mode") != retrieval_mode:
            failures.append(f"{kind}: retrieval_mode must be {retrieval_mode}")
        if metadata.get("enhancement_mode") != enhancement_mode:
            failures.append(f"{kind}: enhancement_mode must be {enhancement_mode}")
    dense_metadata = reports["dense"].snapshot.metadata
    provider = dense_metadata.get("embedding_provider")
    if not isinstance(provider, str) or provider.casefold() in {
        "none",
        "unknown",
        "evaluation-fake",
    }:
        failures.append("dense: a real embedding provider is required")
    bm25_metadata = reports["bm25"].snapshot.metadata
    if (
        bm25_metadata.get("embedding_provider") != "none"
        or bm25_metadata.get("embedding_model") != "none"
        or bm25_metadata.get("embedding_dimension") != 0
    ):
        failures.append("bm25: vector embedding metadata must be disabled")
    if not reports["rerank"].snapshot.metadata.get("reranker_model"):
        failures.append("rerank: reranker_model is required")
    return failures


def _compatibility_failures(
    reports: Mapping[str, LoadedCandidateReport],
) -> list[str]:
    failures: list[str] = []
    dense = reports["dense"]
    for kind in REPORT_KINDS[1:]:
        report = reports[kind]
        if report.snapshot.top_k != dense.snapshot.top_k:
            failures.append(f"{kind}: top_k differs from dense")
        if report.snapshot.case_count != dense.snapshot.case_count:
            failures.append(f"{kind}: case_count differs from dense")
        if report.case_fingerprint != dense.case_fingerprint:
            failures.append(f"{kind}: evaluated cases differ from dense")
        dense_answerability = {
            case_id: _case_metric(case, "no_answer_retrieval_accuracy") is None
            for case_id, case in _holdout_cases(dense).items()
        }
        report_answerability = {
            case_id: _case_metric(case, "no_answer_retrieval_accuracy") is None
            for case_id, case in _holdout_cases(report).items()
        }
        if report_answerability != dense_answerability:
            failures.append(f"{kind}: holdout answerability labels differ from dense")
        for key in COMMON_METADATA_KEYS:
            if report.snapshot.metadata.get(key) != dense.snapshot.metadata.get(key):
                failures.append(f"{kind}: metadata.{key} differs from dense")
    for kind in ("hybrid", "rerank"):
        for key in VECTOR_METADATA_KEYS:
            if reports[kind].snapshot.metadata.get(key) != dense.snapshot.metadata.get(
                key
            ):
                failures.append(f"{kind}: metadata.{key} differs from dense")
    bm25 = reports["bm25"].snapshot.metadata
    hybrid = reports["hybrid"].snapshot.metadata
    rerank = reports["rerank"].snapshot.metadata
    if bm25.get("lexical_score_threshold") != hybrid.get("lexical_score_threshold"):
        failures.append("hybrid: lexical_score_threshold differs from bm25")
    for key in HYBRID_METADATA_KEYS:
        if rerank.get(key) != hybrid.get(key):
            failures.append(f"rerank: metadata.{key} differs from hybrid")
    return failures


def _evidence_failures(
    baseline: LoadedCandidateReport,
    policy: RetrievalCandidatePolicy,
) -> list[str]:
    failures: list[str] = []
    requirements = (
        (
            "total cases",
            baseline.snapshot.case_count,
            policy.minimum_total_cases,
        ),
        (
            "validation cases",
            baseline.validation_case_count,
            policy.minimum_validation_cases,
        ),
        (
            "holdout cases",
            baseline.holdout_case_count,
            policy.minimum_holdout_cases,
        ),
        (
            "holdout answerable cases",
            baseline.holdout_answerable_case_count,
            policy.minimum_holdout_answerable_cases,
        ),
        (
            "holdout no-answer cases",
            baseline.holdout_no_answer_case_count,
            policy.minimum_holdout_no_answer_cases,
        ),
    )
    for label, actual, minimum in requirements:
        if actual < minimum:
            failures.append(f"{label} {actual} is lower than required {minimum}")
    return failures


def _metric(
    report: LoadedCandidateReport,
    name: str,
    failures: list[str],
) -> float | None:
    value = report.holdout_metrics.get(name)
    if value is None:
        failures.append(f"{report.kind}: holdout metric {name} is missing")
        return None
    if name != "p95_duration_ms" and not 0 <= value <= 1:
        failures.append(f"{report.kind}: holdout metric {name} must be within [0, 1]")
        return None
    if name == "p95_duration_ms" and value < 0:
        failures.append(f"{report.kind}: holdout P95 cannot be negative")
        return None
    return float(value)


def _holdout_cases(report: LoadedCandidateReport) -> dict[str, Mapping[str, Any]]:
    """Return validated holdout cases keyed by ID for diagnostic comparison."""

    raw_cases = report.payload.get("cases", [])
    return {
        str(case["case_id"]): case
        for case in raw_cases
        if isinstance(case, Mapping) and case.get("split") == "holdout"
    }


def _case_metric(case: Mapping[str, Any], name: str) -> float | None:
    metrics = case.get("metrics")
    if not isinstance(metrics, Mapping):
        return None
    value = metrics.get(name)
    return (
        float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else None
    )


def _candidate_diagnostics(
    baseline: LoadedCandidateReport,
    candidate: LoadedCandidateReport,
) -> dict[str, Any]:
    """Expose headroom and per-case changes hidden by aggregate metrics.

    Candidate reports intentionally remain the source of truth for the gate. These
    diagnostics do not affect eligibility; they make a ceiling-effect or a single
    ranking regression visible to reviewers.
    """

    baseline_cases = _holdout_cases(baseline)
    candidate_cases = _holdout_cases(candidate)
    answerable_ids = [
        case_id
        for case_id, case in baseline_cases.items()
        if _case_metric(case, "no_answer_retrieval_accuracy") is None
    ]
    no_answer_ids = [
        case_id
        for case_id, case in baseline_cases.items()
        if _case_metric(case, "no_answer_retrieval_accuracy") is not None
    ]

    def top1_rate(
        cases: Mapping[str, Mapping[str, Any]], ids: Sequence[str]
    ) -> float | None:
        values = [
            _case_metric(cases[case_id], "mrr_at_k")
            for case_id in ids
            if case_id in cases
        ]
        values = [value for value in values if value is not None]
        return (sum(value == 1.0 for value in values) / len(values)) if values else None

    changed_rank_count = 0
    answerable_improvements = 0
    answerable_regressions = 0
    for case_id in answerable_ids:
        baseline_case = baseline_cases.get(case_id)
        candidate_case = candidate_cases.get(case_id)
        if baseline_case is None or candidate_case is None:
            continue
        if baseline_case.get("retrieved_document_ids") != candidate_case.get(
            "retrieved_document_ids"
        ):
            changed_rank_count += 1
        baseline_mrr = _case_metric(baseline_case, "mrr_at_k")
        candidate_mrr = _case_metric(candidate_case, "mrr_at_k")
        if baseline_mrr is not None and candidate_mrr is not None:
            if candidate_mrr > baseline_mrr:
                answerable_improvements += 1
            elif candidate_mrr < baseline_mrr:
                answerable_regressions += 1

    non_empty_no_answer = sum(
        bool(candidate_cases.get(case_id, {}).get("retrieved_document_ids"))
        for case_id in no_answer_ids
    )
    candidate_durations = [
        float(case.get("duration_ms"))
        for case in candidate_cases.values()
        if isinstance(case.get("duration_ms"), (int, float))
        and not isinstance(case.get("duration_ms"), bool)
    ]
    baseline_mrr = baseline.holdout_metrics.get("mrr_at_k")
    return {
        "holdout_answerable_case_count": len(answerable_ids),
        "holdout_no_answer_case_count": len(no_answer_ids),
        "baseline_answerable_top1_rate": top1_rate(baseline_cases, answerable_ids),
        "candidate_answerable_top1_rate": top1_rate(candidate_cases, answerable_ids),
        "baseline_mrr_headroom_to_one": (
            round(1.0 - float(baseline_mrr), 6) if baseline_mrr is not None else None
        ),
        "changed_rank_case_count": changed_rank_count,
        "answerable_rank_improvements": answerable_improvements,
        "answerable_rank_regressions": answerable_regressions,
        "candidate_no_answer_non_empty_rate": (
            non_empty_no_answer / len(no_answer_ids) if no_answer_ids else None
        ),
        "candidate_holdout_duration_min_ms": (
            min(candidate_durations) if candidate_durations else None
        ),
        "candidate_holdout_duration_max_ms": (
            max(candidate_durations) if candidate_durations else None
        ),
    }


def _evaluate_candidate(
    kind: str,
    baseline: LoadedCandidateReport,
    candidate: LoadedCandidateReport,
    global_failures: Sequence[str],
    policy: RetrievalCandidatePolicy,
) -> CandidateResult:
    failures = list(global_failures)
    deltas: dict[str, float | None] = {}
    baseline_values: dict[str, float | None] = {}
    candidate_values: dict[str, float | None] = {}
    for name in (*QUALITY_METRICS, "successful_case_rate", "p95_duration_ms"):
        baseline_values[name] = _metric(baseline, name, failures)
        candidate_values[name] = _metric(candidate, name, failures)
    for name in QUALITY_METRICS:
        baseline_value = baseline_values[name]
        candidate_value = candidate_values[name]
        deltas[name] = (
            None
            if baseline_value is None or candidate_value is None
            else candidate_value - baseline_value
        )
        if (
            baseline_value is not None
            and candidate_value is not None
            and candidate_value < baseline_value - policy.allowed_quality_drop
        ):
            failures.append(
                f"{kind}: {name} regressed by "
                f"{baseline_value - candidate_value:.4f}"
            )
    success_rate = candidate_values["successful_case_rate"]
    if success_rate is not None and success_rate < policy.minimum_successful_case_rate:
        failures.append(
            f"{kind}: successful_case_rate {success_rate:.4f} is below "
            f"{policy.minimum_successful_case_rate:.4f}"
        )
    material_gain = any(
        deltas.get(name) is not None and deltas[name] >= minimum
        for name, minimum in (
            ("recall_at_k", policy.minimum_recall_gain),
            ("mrr_at_k", policy.minimum_mrr_gain),
            (
                "no_answer_retrieval_accuracy",
                policy.minimum_no_answer_gain,
            ),
        )
    )
    if not material_gain:
        failures.append(f"{kind}: no material holdout quality gain")
    baseline_p95 = baseline_values["p95_duration_ms"]
    candidate_p95 = candidate_values["p95_duration_ms"]
    p95_increase = (
        None
        if baseline_p95 is None or candidate_p95 is None
        else candidate_p95 - baseline_p95
    )
    p95_multiplier = (
        None
        if baseline_p95 is None or candidate_p95 is None or baseline_p95 <= 0
        else candidate_p95 / baseline_p95
    )
    if p95_increase is not None and p95_increase > policy.maximum_p95_increase_ms:
        failures.append(
            f"{kind}: P95 increase {p95_increase:.1f} ms exceeds "
            f"{policy.maximum_p95_increase_ms:.1f} ms"
        )
    if p95_multiplier is not None and p95_multiplier > policy.maximum_p95_multiplier:
        failures.append(
            f"{kind}: P95 multiplier {p95_multiplier:.3f} exceeds "
            f"{policy.maximum_p95_multiplier:.3f}"
        )
    return CandidateResult(
        eligible=not failures,
        failures=tuple(dict.fromkeys(failures)),
        holdout_metrics=dict(candidate.holdout_metrics),
        deltas_from_dense=deltas,
        p95_increase_ms=p95_increase,
        p95_multiplier=p95_multiplier,
        diagnostics=_candidate_diagnostics(baseline, candidate),
    )


def build_retrieval_candidate_decision(
    report_paths: Mapping[str, str | Path],
    *,
    policy: RetrievalCandidatePolicy | None = None,
) -> RetrievalCandidateDecision:
    """Load four reports and deterministically decide whether one merits rollout."""

    missing = sorted(set(REPORT_KINDS) - set(report_paths))
    unknown = sorted(set(report_paths) - set(REPORT_KINDS))
    if missing or unknown:
        raise ValueError(
            f"candidate report set is incomplete: missing={missing}, unknown={unknown}"
        )
    active_policy = policy or RetrievalCandidatePolicy()
    reports = {kind: _load_report(kind, report_paths[kind]) for kind in REPORT_KINDS}
    global_failures = tuple(
        dict.fromkeys(
            [
                *_identity_failures(reports),
                *_compatibility_failures(reports),
                *_evidence_failures(reports["dense"], active_policy),
            ]
        )
    )
    candidates = {
        kind: _evaluate_candidate(
            kind,
            reports["dense"],
            reports[kind],
            global_failures,
            active_policy,
        )
        for kind in CANDIDATE_KINDS
    }
    eligible = [kind for kind in CANDIDATE_KINDS if candidates[kind].eligible]
    selected = max(
        eligible,
        key=lambda kind: (
            candidates[kind].deltas_from_dense.get("mrr_at_k") or 0.0,
            candidates[kind].deltas_from_dense.get("recall_at_k") or 0.0,
            candidates[kind].deltas_from_dense.get("no_answer_retrieval_accuracy")
            or 0.0,
            -(candidates[kind].holdout_metrics.get("p95_duration_ms") or 0.0),
        ),
        default=None,
    )
    return RetrievalCandidateDecision(
        policy=active_policy,
        reports=reports,
        global_failures=global_failures,
        candidates=candidates,
        decision="GO" if selected else "NO_GO",
        selected_candidate=selected,
    )
