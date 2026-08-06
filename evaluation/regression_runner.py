"""CLI entry point for automatic RAG evaluation regression gates."""

from __future__ import annotations

import argparse
from math import isfinite
from pathlib import Path
from typing import Sequence

from evaluation.regression import (
    RegressionGate,
    load_evaluation_snapshot,
    report_compatibility_issues,
)


DEFAULT_ALLOWED_DROPS = {
    "recall_at_k": 0.02,
    "precision_at_k": 0.02,
    "mrr_at_k": 0.02,
    "top_k_hit_rate": 0.02,
    "no_answer_retrieval_accuracy": 0.0,
}
DEFAULT_MINIMUMS = {"successful_case_rate": 1.0}


def _metric_threshold(value: str) -> tuple[str, float]:
    name, separator, raw_threshold = value.partition("=")
    if not separator or not name.strip():
        raise argparse.ArgumentTypeError("格式必须是 METRIC=VALUE")
    try:
        threshold = float(raw_threshold)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("阈值必须是数字") from exc
    if not isfinite(threshold) or threshold < 0:
        raise argparse.ArgumentTypeError("阈值必须是非负有限数字")
    return name.strip(), threshold


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare a RAG report with a baseline")
    parser.add_argument("--baseline", required=True, help="Baseline JSON report")
    parser.add_argument("--current", required=True, help="Current JSON report")
    parser.add_argument(
        "--allowed-drop",
        action="append",
        type=_metric_threshold,
        default=[],
        metavar="METRIC=VALUE",
        help="Override or add an allowed absolute metric drop",
    )
    parser.add_argument(
        "--minimum",
        action="append",
        type=_metric_threshold,
        default=[],
        metavar="METRIC=VALUE",
        help="Override or add an absolute metric minimum",
    )
    parser.add_argument(
        "--no-default-policy",
        action="store_true",
        help="Use only explicitly supplied allowed drops and minimums",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        baseline = load_evaluation_snapshot(Path(args.baseline))
        current = load_evaluation_snapshot(Path(args.current))
    except (OSError, TypeError, ValueError) as exc:
        print(f"RAG regression gate: ERROR\n- {exc}")
        return 2

    compatibility_issues = report_compatibility_issues(baseline, current)
    if compatibility_issues:
        print("RAG regression gate: INCOMPATIBLE")
        for issue in compatibility_issues:
            print(f"- {issue}")
        return 2

    allowed_drops = {} if args.no_default_policy else dict(DEFAULT_ALLOWED_DROPS)
    minimums = {} if args.no_default_policy else dict(DEFAULT_MINIMUMS)
    allowed_drops.update(dict(args.allowed_drop))
    minimums.update(dict(args.minimum))
    result = RegressionGate(
        allowed_drops=allowed_drops,
        minimums=minimums,
    ).evaluate(baseline, current)

    if not result.passed:
        print("RAG regression gate: FAIL")
        for failure in result.failures:
            print(
                f"- {failure.metric}: {failure.reason}; "
                f"baseline={failure.baseline!r}, current={failure.current!r}"
            )
        return 1

    checked = ", ".join(result.checked_metrics) or "none"
    print(f"RAG regression gate: PASS\n- checked_metrics: {checked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
