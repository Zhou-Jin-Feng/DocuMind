"""Atomic file output for answer quality evaluation reports."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from evaluation.answer_models import AnswerEvaluationReport


def validate_answer_report_paths(
    json_path: str | Path,
    markdown_path: str | Path,
) -> tuple[Path, Path]:
    """Reject invalid destinations before any provider-backed evaluation starts."""

    json_output = Path(json_path)
    markdown_output = Path(markdown_path)
    if json_output.resolve() == markdown_output.resolve():
        raise ValueError("JSON 和 Markdown 报告路径不能相同")
    for output in (json_output, markdown_output):
        if output.exists() and output.is_dir():
            raise IsADirectoryError(f"报告路径不能是目录: {output}")
        if output.parent.exists() and not output.parent.is_dir():
            raise NotADirectoryError(f"报告父路径不是目录: {output.parent}")
    return json_output, markdown_output


def _atomic_write_text(path: Path, content: str) -> Path:
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
    return path


def write_answer_reports(
    report: AnswerEvaluationReport,
    json_path: str | Path,
    markdown_path: str | Path,
) -> tuple[Path, Path]:
    """Write complete JSON and Markdown reports without exposing partial files."""

    if not isinstance(report, AnswerEvaluationReport):
        raise TypeError("report 必须是 AnswerEvaluationReport")
    json_output, markdown_output = validate_answer_report_paths(
        json_path,
        markdown_path,
    )
    _atomic_write_text(json_output, report.to_json())
    _atomic_write_text(markdown_output, report.to_markdown())
    return json_output, markdown_output
