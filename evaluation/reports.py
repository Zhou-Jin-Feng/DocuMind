"""File output helpers for evaluation reports."""

from pathlib import Path

from evaluation.models import EvaluationReport


def write_json_report(report: EvaluationReport, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.to_json(), encoding="utf-8")
    return output


def write_markdown_report(report: EvaluationReport, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.to_markdown(), encoding="utf-8")
    return output
