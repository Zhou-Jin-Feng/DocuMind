"""CLI for producing a strict four-mode v1.7 comparison report."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from evaluation.comparison import ENHANCEMENT_MODES, build_evaluation_comparison
from evaluation.regression import load_evaluation_snapshot


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare baseline, rewrite, rerank, and rewrite-rerank reports"
    )
    for mode in ENHANCEMENT_MODES:
        parser.add_argument(f"--{mode}", required=True, help=f"{mode} JSON report")
    parser.add_argument(
        "--output-json",
        default="evaluation/reports/v1_7_1_comparison.json",
    )
    parser.add_argument(
        "--output-markdown",
        default="evaluation/reports/v1_7_1_comparison.md",
    )
    args = parser.parse_args(argv)

    try:
        comparison = build_evaluation_comparison(
            {
                mode: load_evaluation_snapshot(getattr(args, mode.replace("-", "_")))
                for mode in ENHANCEMENT_MODES
            }
        )
    except (OSError, TypeError, ValueError) as exc:
        print(f"RAG enhancement comparison: ERROR\n- {exc}")
        return 2

    json_path = Path(args.output_json)
    markdown_path = Path(args.output_markdown)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(comparison.to_json(), encoding="utf-8")
    markdown_path.write_text(comparison.to_markdown(), encoding="utf-8")
    print(comparison.to_markdown())
    print(f"json_comparison={json_path}")
    print(f"markdown_comparison={markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
