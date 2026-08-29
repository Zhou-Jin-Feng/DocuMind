"""CLI for deterministic single-document retrieval quality reports."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path
from typing import Sequence

from evaluation.retrieve_quality import (
    load_retrieve_quality_dataset,
    quality_invariant_failures,
    run_retrieve_quality,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "evaluation" / "datasets" / "retrieve_quality_v1.json"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run deterministic DocuMind /retrieve quality regression"
    )
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--markdown-output", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    json_output = Path(args.json_output)
    markdown_output = Path(args.markdown_output)
    if json_output.resolve() == markdown_output.resolve():
        raise ValueError("JSON and Markdown outputs must be different files")
    dataset = load_retrieve_quality_dataset(args.dataset)
    report = run_retrieve_quality(dataset)
    _atomic_write(json_output, report.to_json())
    _atomic_write(markdown_output, report.to_markdown())
    failures = quality_invariant_failures(report)
    if failures:
        print("Retrieve quality report: FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(
        "Retrieve quality report: PASS\n"
        f"- cases: {len(report.case_results)}\n"
        f"- json: {json_output}\n"
        f"- markdown: {markdown_output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
