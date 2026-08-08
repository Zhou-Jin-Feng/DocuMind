"""CLI for creating a real Embedding retrieval baseline."""

from __future__ import annotations

import argparse
from math import isfinite
from pathlib import Path
from typing import Sequence

from app.config import settings
from evaluation.fingerprints import file_sha256, text_corpus_sha256
from evaluation.production import (
    build_configured_hybrid_retrieval_adapter,
    build_configured_retrieval_adapter,
    build_lexical_retrieval_adapter,
    load_text_documents,
)
from evaluation.reports import write_json_report, write_markdown_report
from evaluation.runner import EvaluationRunner, load_golden_dataset


def _default_report_stem(
    provider: str,
    score_threshold: float | None,
    retrieval_mode: str = "dense",
    *,
    dense_weight: float = 1.0,
    lexical_weight: float = 1.0,
    rrf_k: int = 60,
    candidate_multiplier: int = 5,
    lexical_score_threshold: float | None = None,
) -> str:
    """Keep threshold experiments from overwriting the unfiltered baseline."""

    mode_label = "" if retrieval_mode == "dense" else f"_{retrieval_mode}"
    if score_threshold is None:
        stem = f"{provider}{mode_label}_retrieval_baseline"
    else:
        label = format(score_threshold, "g").replace("-", "minus").replace(".", "_")
        stem = f"{provider}{mode_label}_retrieval_threshold_{label}"
    calibration: list[str] = []
    if retrieval_mode == "hybrid":
        if dense_weight != 1.0:
            calibration.append(f"dw_{format(dense_weight, 'g').replace('.', '_')}")
        if lexical_weight != 1.0:
            calibration.append(f"lw_{format(lexical_weight, 'g').replace('.', '_')}")
        if rrf_k != 60:
            calibration.append(f"rrfk_{rrf_k}")
        if candidate_multiplier != 5:
            calibration.append(f"cand_{candidate_multiplier}")
    if lexical_score_threshold is not None:
        label = format(lexical_score_threshold, "g").replace("-", "minus").replace(".", "_")
        calibration.append(f"lex_{label}")
    return f"{stem}_{'_'.join(calibration)}" if calibration else stem


def _validate_calibration_args(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> None:
    rrf_options_changed = any(
        (
            args.dense_weight != 1.0,
            args.lexical_weight != 1.0,
            args.rrf_k != 60,
            args.candidate_multiplier != 5,
        )
    )
    for name in ("score_threshold", "lexical_score_threshold"):
        value = getattr(args, name)
        if value is not None and (not isfinite(value) or value < 0):
            parser.error(f"--{name.replace('_', '-')} must be a non-negative finite number")
    if args.retrieval_mode == "dense":
        if args.lexical_score_threshold is not None:
            parser.error("--lexical-score-threshold only applies to BM25 or Hybrid")
        if rrf_options_changed:
            parser.error("RRF parameters only apply to Hybrid")
        return
    if args.retrieval_mode == "bm25":
        if args.score_threshold is not None:
            parser.error("--score-threshold is not supported for BM25-only")
        if rrf_options_changed:
            parser.error("RRF parameters only apply to Hybrid")
        return
    if args.rrf_k <= 0:
        parser.error("--rrf-k must be a positive integer")
    if args.candidate_multiplier <= 0:
        parser.error("--candidate-multiplier must be a positive integer")
    for name in ("dense_weight", "lexical_weight"):
        value = getattr(args, name)
        if not isfinite(value) or value < 0:
            parser.error(f"--{name.replace('_', '-')} must be a non-negative finite number")
    if args.dense_weight == 0 and args.lexical_weight == 0:
        parser.error("--dense-weight and --lexical-weight cannot both be zero")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a real Embedding retrieval baseline from the golden dataset"
    )
    parser.add_argument(
        "--dataset",
        default="evaluation/datasets/golden_dataset.jsonl",
        help="JSONL golden dataset path",
    )
    parser.add_argument(
        "--documents-dir",
        default="evaluation/datasets/documents",
        help="TXT fixture directory; filename stem becomes document_id",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="Embedding provider; defaults to DEFAULT_EMBEDDING_PROVIDER",
    )
    parser.add_argument(
        "--retrieval-mode",
        choices=("dense", "bm25", "hybrid"),
        default="dense",
        help="Retrieval strategy to evaluate; Web remains Dense-only",
    )
    parser.add_argument(
        "--collection-name",
        default="rag_evaluation",
        help="Temporary or persistent Chroma collection name",
    )
    parser.add_argument(
        "--score-threshold",
        type=float,
        default=None,
        help="Maximum vector distance to accept; defaults to no threshold",
    )
    parser.add_argument(
        "--lexical-score-threshold",
        type=float,
        default=None,
        help="BM25 minimum lexical score for BM25 or Hybrid calibration",
    )
    parser.add_argument("--dense-weight", type=float, default=1.0)
    parser.add_argument("--lexical-weight", type=float, default=1.0)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--candidate-multiplier", type=int, default=5)
    parser.add_argument(
        "--persist-directory",
        default="./data/evaluation_chroma_db",
        help="Chroma persistence directory",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="JSON report path; defaults to evaluation/reports/{provider}_retrieval_baseline.json",
    )
    parser.add_argument(
        "--output-markdown",
        default=None,
        help="Markdown report path; defaults to evaluation/reports/{provider}_retrieval_baseline.md",
    )
    args = parser.parse_args(argv)
    _validate_calibration_args(parser, args)

    provider = args.provider or settings.default_embedding_provider
    dataset_path = Path(args.dataset)
    cases = load_golden_dataset(dataset_path)
    documents = load_text_documents(args.documents_dir)
    adapter = None
    try:
        if args.retrieval_mode == "dense":
            adapter, summary = build_configured_retrieval_adapter(
                documents,
                provider=provider,
                collection_name=args.collection_name,
                persist_directory=args.persist_directory,
                score_threshold=args.score_threshold,
            )
        elif args.retrieval_mode == "bm25":
            adapter, summary = build_lexical_retrieval_adapter(
                documents,
                lexical_score_threshold=args.lexical_score_threshold,
            )
        else:
            adapter, summary = build_configured_hybrid_retrieval_adapter(
                documents,
                provider=provider,
                collection_name=args.collection_name,
                persist_directory=args.persist_directory,
                score_threshold=args.score_threshold,
                rrf_k=args.rrf_k,
                dense_weight=args.dense_weight,
                lexical_weight=args.lexical_weight,
                candidate_multiplier=args.candidate_multiplier,
                lexical_score_threshold=args.lexical_score_threshold,
            )
        case_top_k_values = sorted({case.top_k for case in cases})
        report = EvaluationRunner(
            adapter,
            dataset_name=(
                f"{provider}-retrieval-baseline"
                if args.retrieval_mode == "dense"
                else f"{provider}-{args.retrieval_mode}-retrieval-baseline"
            ),
            default_top_k=settings.retrieval_top_k,
            metadata={
                **summary.to_dict(),
                "case_count": len(cases),
                "case_top_k_values": case_top_k_values,
                "score_threshold": args.score_threshold,
                "lexical_score_threshold": args.lexical_score_threshold,
                "dense_weight": args.dense_weight,
                "lexical_weight": args.lexical_weight,
                "rrf_k": args.rrf_k,
                "candidate_multiplier": args.candidate_multiplier,
                "retrieval_mode": args.retrieval_mode,
                "dataset_path": dataset_path.as_posix(),
                "documents_directory": Path(args.documents_dir).as_posix(),
                "dataset_sha256": file_sha256(dataset_path),
                "documents_sha256": text_corpus_sha256(args.documents_dir),
            },
        ).run(cases)
    finally:
        if adapter is not None:
            adapter.close()

    output_dir = Path("evaluation/reports")
    report_stem = _default_report_stem(
        provider,
        args.score_threshold,
        args.retrieval_mode,
        dense_weight=args.dense_weight,
        lexical_weight=args.lexical_weight,
        rrf_k=args.rrf_k,
        candidate_multiplier=args.candidate_multiplier,
        lexical_score_threshold=args.lexical_score_threshold,
    )
    json_path = Path(args.output_json or output_dir / f"{report_stem}.json")
    markdown_path = Path(
        args.output_markdown or output_dir / f"{report_stem}.md"
    )
    write_json_report(report, json_path)
    write_markdown_report(report, markdown_path)
    print(f"indexing_summary={summary}")
    print(report.to_markdown())
    print(f"json_report={json_path}")
    print(f"markdown_report={markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
