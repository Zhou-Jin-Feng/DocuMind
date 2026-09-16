"""CLI for creating a real Embedding retrieval baseline."""

from __future__ import annotations

import argparse
from importlib.metadata import version as package_version
from math import isfinite
from pathlib import Path
from typing import Sequence

from app.config import settings
from evaluation.fingerprints import file_sha256, text_corpus_sha256, text_file_sha256
from evaluation.models import GoldenCase
from evaluation.production import (
    build_configured_hybrid_retrieval_adapter,
    build_configured_retrieval_adapter,
    build_lexical_retrieval_adapter,
    enhance_retrieval_adapter,
    load_text_documents,
)
from evaluation.reports import write_json_report, write_markdown_report
from evaluation.runner import EvaluationRunner, load_golden_dataset

DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parents[1] / "artifacts" / "evaluation"


def _select_cases_by_split(cases: Sequence[GoldenCase], split: str) -> list[GoldenCase]:
    if split not in {"all", "validation", "holdout"}:
        raise ValueError(f"不支持的评测 split: {split}")
    selected = (
        list(cases)
        if split == "all"
        else [case for case in cases if case.split == split]
    )
    if not selected:
        raise ValueError(f"数据集没有 {split} 案例")
    return selected


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
    enhancement_mode: str = "baseline",
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
        label = (
            format(lexical_score_threshold, "g").replace("-", "minus").replace(".", "_")
        )
        calibration.append(f"lex_{label}")
    if calibration:
        stem = f"{stem}_{'_'.join(calibration)}"
    if enhancement_mode != "baseline":
        stem = f"{stem}_{enhancement_mode.replace('-', '_')}"
    return stem


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
            parser.error(
                f"--{name.replace('_', '-')} must be a non-negative finite number"
            )
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
            parser.error(
                f"--{name.replace('_', '-')} must be a non-negative finite number"
            )
    if args.dense_weight == 0 and args.lexical_weight == 0:
        parser.error("--dense-weight and --lexical-weight cannot both be zero")


def _validate_enhancement_args(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> None:
    positive_integer_names = (
        "max_rewrites",
        "rewrite_max_tokens",
        "query_rrf_k",
        "per_query_candidate_multiplier",
        "rerank_candidate_multiplier",
        "reranker_batch_size",
    )
    for name in positive_integer_names:
        value = getattr(args, name)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            parser.error(f"--{name.replace('_', '-')} must be a positive integer")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a real Embedding retrieval baseline from the golden dataset"
    )
    parser.add_argument(
        "--dataset",
        default=str(
            Path(__file__).resolve().parent / "datasets" / "golden_dataset.jsonl"
        ),
        help="JSONL golden dataset path",
    )
    parser.add_argument(
        "--documents-dir",
        default=str(Path(__file__).resolve().parent / "datasets" / "documents"),
        help="TXT fixture directory; filename stem becomes document_id",
    )
    parser.add_argument(
        "--split",
        choices=("all", "validation", "holdout"),
        default="all",
        help="Run only one frozen dataset split; defaults to all cases",
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
        help="Milvus Collection used for this evaluation",
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
        "--enhancement-mode",
        choices=("baseline", "rewrite", "rerank", "rewrite-rerank"),
        default="baseline",
        help="Optional v1.7 retrieval experiment; Web remains unchanged",
    )
    parser.add_argument(
        "--rewrite-provider",
        default=None,
        help="LLM provider for Query Rewrite; defaults to DEFAULT_LLM_PROVIDER",
    )
    parser.add_argument("--rewrite-model", default=None)
    parser.add_argument(
        "--rewrite-map",
        default=None,
        help="Pre-generated rewrite artifact for reproducible offline evaluation",
    )
    parser.add_argument("--max-rewrites", type=int, default=2)
    parser.add_argument("--rewrite-max-tokens", type=int, default=256)
    parser.add_argument("--query-rrf-k", type=int, default=60)
    parser.add_argument("--per-query-candidate-multiplier", type=int, default=1)
    parser.add_argument(
        "--reranker-model",
        default="BAAI/bge-reranker-base",
    )
    parser.add_argument("--reranker-batch-size", type=int, default=16)
    parser.add_argument("--reranker-device", default=None)
    parser.add_argument(
        "--reranker-local-files-only",
        action="store_true",
        help="Load the reranker only from the local Hugging Face cache",
    )
    parser.add_argument("--rerank-candidate-multiplier", type=int, default=5)
    parser.add_argument(
        "--milvus-uri",
        default=settings.milvus_uri,
        help="Milvus server URI",
    )
    parser.add_argument(
        "--milvus-token",
        default=settings.milvus_token,
        help="Optional Milvus authentication token",
    )
    parser.add_argument(
        "--milvus-db-name",
        default=settings.milvus_db_name,
        help="Milvus database name",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="JSON report path; defaults to project artifacts/evaluation/{provider}_retrieval_baseline.json",
    )
    parser.add_argument(
        "--output-markdown",
        default=None,
        help=(
            "Markdown report path; defaults to "
            "project artifacts/evaluation/{provider}_retrieval_baseline.md"
        ),
    )
    args = parser.parse_args(argv)
    _validate_calibration_args(parser, args)
    _validate_enhancement_args(parser, args)
    if args.rewrite_map and args.enhancement_mode not in {
        "rewrite",
        "rewrite-rerank",
    }:
        parser.error("--rewrite-map requires rewrite or rewrite-rerank mode")

    provider = args.provider or settings.default_embedding_provider
    dataset_path = Path(args.dataset)
    all_cases = load_golden_dataset(dataset_path)
    try:
        cases = _select_cases_by_split(all_cases, args.split)
    except ValueError as exc:
        parser.error(str(exc))
    dataset_sha256 = text_file_sha256(dataset_path)
    documents = load_text_documents(args.documents_dir)
    adapter = None
    rewrite_provider = None
    rewrite_model = None
    rewrite_map_sha256 = None
    rewrite_artifact_version = None
    rewrite_artifact_max_rewrites = None
    rewrite_generation_max_tokens = None
    rewrite_temperature = None
    rewrite_prompt_sha256 = None
    reranker_library_version = None
    try:
        if args.retrieval_mode == "dense":
            adapter, summary = build_configured_retrieval_adapter(
                documents,
                provider=provider,
                collection_name=args.collection_name,
                milvus_uri=args.milvus_uri,
                milvus_token=args.milvus_token,
                milvus_db_name=args.milvus_db_name,
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
                milvus_uri=args.milvus_uri,
                milvus_token=args.milvus_token,
                milvus_db_name=args.milvus_db_name,
                score_threshold=args.score_threshold,
                rrf_k=args.rrf_k,
                dense_weight=args.dense_weight,
                lexical_weight=args.lexical_weight,
                candidate_multiplier=args.candidate_multiplier,
                lexical_score_threshold=args.lexical_score_threshold,
            )
        query_rewriter = None
        reranker = None
        if args.enhancement_mode in {"rewrite", "rewrite-rerank"}:
            if args.rewrite_map:
                from evaluation.rewrite_artifacts import load_rewrite_artifact

                artifact = load_rewrite_artifact(
                    args.rewrite_map,
                    expected_dataset_sha256=dataset_sha256,
                    expected_questions=[case.question for case in cases],
                )
                query_rewriter = artifact.to_rewriter(max_rewrites=args.max_rewrites)
                rewrite_provider = artifact.provider
                rewrite_model = artifact.model
                rewrite_map_sha256 = file_sha256(args.rewrite_map)
                rewrite_artifact_version = artifact.artifact_version
                rewrite_artifact_max_rewrites = artifact.max_rewrites
                rewrite_generation_max_tokens = artifact.max_tokens
                rewrite_temperature = artifact.temperature
                rewrite_prompt_sha256 = artifact.prompt_sha256
            else:
                from app.core.generator import UniversalLLMClient
                from app.core.query_rewriter import LLMQueryRewriter

                llm_client = UniversalLLMClient(
                    provider=args.rewrite_provider or settings.default_llm_provider,
                    model=args.rewrite_model,
                )
                query_rewriter = LLMQueryRewriter(
                    llm_client,
                    max_rewrites=args.max_rewrites,
                    max_tokens=args.rewrite_max_tokens,
                )
                rewrite_provider = llm_client.provider
                rewrite_model = llm_client.model
                rewrite_generation_max_tokens = query_rewriter.config.max_tokens
                rewrite_temperature = query_rewriter.config.temperature
                rewrite_prompt_sha256 = query_rewriter.prompt_sha256
        if args.enhancement_mode in {"rerank", "rewrite-rerank"}:
            from app.core.reranker import CrossEncoderReranker

            reranker_library_version = package_version("sentence-transformers")
            reranker = CrossEncoderReranker(
                args.reranker_model,
                batch_size=args.reranker_batch_size,
                device=args.reranker_device,
                local_files_only=args.reranker_local_files_only,
            )
        if query_rewriter is not None or reranker is not None:
            enhance_retrieval_adapter(
                adapter,
                query_rewriter=query_rewriter,
                reranker=reranker,
                query_rrf_k=args.query_rrf_k,
                per_query_candidate_multiplier=args.per_query_candidate_multiplier,
                rerank_candidate_multiplier=args.rerank_candidate_multiplier,
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
                "enhancement_mode": args.enhancement_mode,
                "distance_metric": "L2" if args.retrieval_mode == "dense" else None,
                "evaluation_split": args.split,
                "rewrite_provider": rewrite_provider,
                "rewrite_model": rewrite_model,
                "rewrite_map_path": (
                    Path(args.rewrite_map).as_posix() if args.rewrite_map else None
                ),
                "rewrite_map_sha256": rewrite_map_sha256,
                "rewrite_artifact_version": rewrite_artifact_version,
                "rewrite_artifact_max_rewrites": rewrite_artifact_max_rewrites,
                "rewrite_generation_max_tokens": rewrite_generation_max_tokens,
                "rewrite_temperature": rewrite_temperature,
                "rewrite_prompt_sha256": rewrite_prompt_sha256,
                "max_rewrites": (
                    args.max_rewrites
                    if args.enhancement_mode in {"rewrite", "rewrite-rerank"}
                    else None
                ),
                "rewrite_max_tokens": (
                    args.rewrite_max_tokens
                    if args.enhancement_mode in {"rewrite", "rewrite-rerank"}
                    and not args.rewrite_map
                    else None
                ),
                "query_rrf_k": (
                    args.query_rrf_k
                    if args.enhancement_mode in {"rewrite", "rewrite-rerank"}
                    else None
                ),
                "per_query_candidate_multiplier": (
                    args.per_query_candidate_multiplier
                    if args.enhancement_mode in {"rewrite", "rewrite-rerank"}
                    else None
                ),
                "reranker_model": (
                    args.reranker_model
                    if args.enhancement_mode in {"rerank", "rewrite-rerank"}
                    else None
                ),
                "sentence_transformers_version": reranker_library_version,
                "reranker_batch_size": (
                    args.reranker_batch_size
                    if args.enhancement_mode in {"rerank", "rewrite-rerank"}
                    else None
                ),
                "reranker_device": (
                    args.reranker_device
                    if args.enhancement_mode in {"rerank", "rewrite-rerank"}
                    else None
                ),
                "reranker_local_files_only": (
                    args.reranker_local_files_only
                    if args.enhancement_mode in {"rerank", "rewrite-rerank"}
                    else None
                ),
                "rerank_candidate_multiplier": (
                    args.rerank_candidate_multiplier
                    if args.enhancement_mode in {"rerank", "rewrite-rerank"}
                    else None
                ),
                "dataset_path": dataset_path.as_posix(),
                "documents_directory": Path(args.documents_dir).as_posix(),
                "dataset_sha256": dataset_sha256,
                "documents_sha256": text_corpus_sha256(args.documents_dir),
            },
        ).run(cases)
    finally:
        if adapter is not None:
            adapter.close()

    output_dir = DEFAULT_OUTPUT_ROOT
    report_stem = _default_report_stem(
        provider,
        args.score_threshold,
        args.retrieval_mode,
        dense_weight=args.dense_weight,
        lexical_weight=args.lexical_weight,
        rrf_k=args.rrf_k,
        candidate_multiplier=args.candidate_multiplier,
        lexical_score_threshold=args.lexical_score_threshold,
        enhancement_mode=args.enhancement_mode,
    )
    json_path = Path(args.output_json or output_dir / f"{report_stem}.json")
    markdown_path = Path(args.output_markdown or output_dir / f"{report_stem}.md")
    write_json_report(report, json_path)
    write_markdown_report(report, markdown_path)
    print(f"indexing_summary={summary}")
    print(report.to_markdown())
    print(f"json_report={json_path}")
    print(f"markdown_report={markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
