"""CLI for producing the deterministic P2 retrieval candidate decision."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Sequence

from evaluation.retrieval_candidate_gate import (
    REPORT_KINDS,
    build_retrieval_candidate_decision,
)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate P2 BM25, Hybrid and Reranker rollout evidence"
    )
    for kind in REPORT_KINDS:
        parser.add_argument(f"--{kind}", required=True, help=f"{kind} JSON report")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-markdown", required=True)
    args = parser.parse_args(argv)
    json_path = Path(args.output_json)
    markdown_path = Path(args.output_markdown)
    if json_path.resolve() == markdown_path.resolve():
        parser.error("--output-json and --output-markdown must be different")
    try:
        decision = build_retrieval_candidate_decision(
            {kind: getattr(args, kind) for kind in REPORT_KINDS}
        )
        _atomic_write(json_path, decision.to_json())
        _atomic_write(markdown_path, decision.to_markdown())
    except (OSError, TypeError, ValueError) as exc:
        print(f"P2 retrieval candidate gate: ERROR\n- {exc}")
        return 2
    print(f"P2 retrieval candidate gate: {decision.decision}")
    print(decision.to_markdown())
    print(f"json_decision={json_path}")
    print(f"markdown_decision={markdown_path}")
    return 0 if decision.decision == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
