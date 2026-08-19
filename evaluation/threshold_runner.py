"""CLI for validation-only threshold selection and one-shot holdout decisions."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Sequence
from uuid import uuid4

from evaluation.fingerprints import file_sha256, text_file_sha256
from evaluation.runner import load_golden_dataset
from evaluation.threshold_calibration import (
    build_holdout_decision,
    build_validation_calibration,
    calibration_to_json,
    calibration_to_markdown,
    load_json_object,
)


def _atomic_write(path: str | Path, content: str) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()
    return output


def _write_outputs(payload, json_path: str | Path, markdown_path: str | Path) -> None:
    json_output = Path(json_path).resolve()
    markdown_output = Path(markdown_path).resolve()
    if json_output == markdown_output:
        raise ValueError("JSON 和 Markdown 输出路径不能相同")
    _atomic_write(json_output, calibration_to_json(payload))
    _atomic_write(markdown_output, calibration_to_markdown(payload))


def _generated_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Calibrate Dense L2 retrieval threshold"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan = subparsers.add_parser("scan", help="Select a candidate from validation only")
    scan.add_argument("--dataset", required=True)
    scan.add_argument("--validation-report", required=True)
    scan.add_argument("--output-json", required=True)
    scan.add_argument("--output-markdown", required=True)

    decide = subparsers.add_parser(
        "decide", help="Evaluate the frozen candidate once on holdout"
    )
    decide.add_argument("--dataset", required=True)
    decide.add_argument("--validation-calibration", required=True)
    decide.add_argument("--holdout-report", required=True)
    decide.add_argument("--output-json", required=True)
    decide.add_argument("--output-markdown", required=True)
    args = parser.parse_args(argv)

    dataset_path = Path(args.dataset)
    cases = load_golden_dataset(dataset_path)
    dataset_sha256 = text_file_sha256(dataset_path)
    if args.command == "scan":
        report_path = Path(args.validation_report)
        payload = build_validation_calibration(
            cases,
            load_json_object(report_path),
            dataset_sha256=dataset_sha256,
            source_report_path=report_path.as_posix(),
            source_report_sha256=file_sha256(report_path),
            generated_at=_generated_at(),
        )
    else:
        calibration_path = Path(args.validation_calibration)
        report_path = Path(args.holdout_report)
        payload = build_holdout_decision(
            load_json_object(calibration_path),
            cases,
            load_json_object(report_path),
            dataset_sha256=dataset_sha256,
            validation_calibration_path=calibration_path.as_posix(),
            validation_calibration_sha256=file_sha256(calibration_path),
            source_report_path=report_path.as_posix(),
            source_report_sha256=file_sha256(report_path),
            generated_at=_generated_at(),
        )
    _write_outputs(payload, args.output_json, args.output_markdown)
    print(calibration_to_markdown(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
