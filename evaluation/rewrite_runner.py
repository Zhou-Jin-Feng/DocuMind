"""CLI for generating a strict query-rewrite artifact through a real LLM."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from app.config import settings
from app.core.generator import UniversalLLMClient
from app.core.query_rewriter import LLMQueryRewriter
from evaluation.fingerprints import file_sha256
from evaluation.rewrite_artifacts import build_rewrite_artifact
from evaluation.runner import load_golden_dataset


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a reproducible Query Rewrite artifact for evaluation"
    )
    parser.add_argument("--dataset", required=True)
    parser.add_argument(
        "--provider",
        default=None,
        help="LLM provider; defaults to DEFAULT_LLM_PROVIDER",
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-rewrites", type=int, default=2)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.max_rewrites <= 0:
        parser.error("--max-rewrites must be a positive integer")
    if args.max_tokens <= 0:
        parser.error("--max-tokens must be a positive integer")

    dataset_path = Path(args.dataset)
    cases = load_golden_dataset(dataset_path)
    client = UniversalLLMClient(
        provider=args.provider or settings.default_llm_provider,
        model=args.model,
    )
    artifact = build_rewrite_artifact(
        cases,
        LLMQueryRewriter(
            client,
            max_rewrites=args.max_rewrites,
            max_tokens=args.max_tokens,
        ),
        provider=client.provider,
        model=client.model,
        max_rewrites=args.max_rewrites,
        dataset_sha256=file_sha256(dataset_path),
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(artifact.to_json(), encoding="utf-8")
    print(f"rewrite_artifact={output_path}")
    print(f"case_count={len(cases)}")
    print(f"provider={artifact.provider}")
    print(f"model={artifact.model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
