"""CLI for generating a strict query-rewrite artifact through a real LLM."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from app.config import settings
from app.core.generator import UniversalLLMClient
from app.core.query_rewriter import LLMQueryRewriter
from evaluation.fingerprints import file_sha256
from evaluation.rewrite_artifacts import (
    build_rewrite_artifact,
    load_rewrite_artifact_file,
)
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
    parser.add_argument("--request-timeout", type=float, default=30.0)
    parser.add_argument(
        "--checkpoint",
        default=None,
        help="Partial artifact path; defaults to OUTPUT.partial",
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.max_rewrites <= 0:
        parser.error("--max-rewrites must be a positive integer")
    if args.max_tokens <= 0:
        parser.error("--max-tokens must be a positive integer")
    if args.request_timeout <= 0:
        parser.error("--request-timeout must be a positive number")

    dataset_path = Path(args.dataset)
    cases = load_golden_dataset(dataset_path)
    dataset_sha256 = file_sha256(dataset_path)
    client = UniversalLLMClient(
        provider=args.provider or settings.default_llm_provider,
        model=args.model,
        request_timeout_seconds=args.request_timeout,
    )
    rewriter = LLMQueryRewriter(
        client,
        max_rewrites=args.max_rewrites,
        max_tokens=args.max_tokens,
    )
    output_path = Path(args.output)
    checkpoint_path = Path(
        args.checkpoint or f"{output_path}.partial"
    )
    existing_rewrites = None
    if checkpoint_path.is_file():
        checkpoint = load_rewrite_artifact_file(checkpoint_path)
        expected_fields = {
            "provider": client.provider,
            "model": client.model,
            "max_rewrites": args.max_rewrites,
            "max_tokens": rewriter.config.max_tokens,
            "temperature": rewriter.config.temperature,
            "prompt_sha256": rewriter.prompt_sha256,
            "dataset_sha256": dataset_sha256,
        }
        mismatches = [
            name
            for name, expected in expected_fields.items()
            if getattr(checkpoint, name) != expected
        ]
        if mismatches:
            raise ValueError(
                "Rewrite checkpoint 配置不匹配: " + ", ".join(mismatches)
            )
        expected_questions = {" ".join(case.question.split()) for case in cases}
        unknown_questions = sorted(set(checkpoint.rewrites) - expected_questions)
        if unknown_questions:
            raise ValueError(
                f"Rewrite checkpoint 包含未知问题: {unknown_questions}"
            )
        existing_rewrites = checkpoint.rewrites
        print(f"checkpoint_resumed={len(existing_rewrites)}/{len(cases)}", flush=True)

    def write_checkpoint(artifact, completed, total):
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = checkpoint_path.with_name(f"{checkpoint_path.name}.tmp")
        temporary.write_text(artifact.to_json(), encoding="utf-8")
        temporary.replace(checkpoint_path)
        print(f"rewrite_progress={completed}/{total}", flush=True)

    artifact = build_rewrite_artifact(
        cases,
        rewriter,
        provider=client.provider,
        model=client.model,
        max_rewrites=args.max_rewrites,
        max_tokens=rewriter.config.max_tokens,
        temperature=rewriter.config.temperature,
        prompt_sha256=rewriter.prompt_sha256,
        dataset_sha256=dataset_sha256,
        existing_rewrites=existing_rewrites,
        progress_callback=write_checkpoint,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output_path.with_name(f"{output_path.name}.tmp")
    temporary_output.write_text(artifact.to_json(), encoding="utf-8")
    temporary_output.replace(output_path)
    checkpoint_path.unlink(missing_ok=True)
    print(f"rewrite_artifact={output_path}")
    print(f"case_count={len(cases)}")
    print(f"provider={artifact.provider}")
    print(f"model={artifact.model}")
    print(f"prompt_sha256={artifact.prompt_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
