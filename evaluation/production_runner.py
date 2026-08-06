"""CLI for creating a real Embedding retrieval baseline."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.config import settings
from evaluation.fingerprints import file_sha256, text_corpus_sha256
from evaluation.production import (
    build_configured_retrieval_adapter,
    load_text_documents,
)
from evaluation.reports import write_json_report, write_markdown_report
from evaluation.runner import EvaluationRunner, load_golden_dataset


def _default_report_stem(provider: str, score_threshold: float | None) -> str:
    """Keep threshold experiments from overwriting the unfiltered baseline."""

    if score_threshold is None:
        return f"{provider}_retrieval_baseline"
    label = format(score_threshold, "g").replace("-", "minus").replace(".", "_")
    return f"{provider}_retrieval_threshold_{label}"


def main() -> int:
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
    args = parser.parse_args()

    provider = args.provider or settings.default_embedding_provider
    dataset_path = Path(args.dataset)
    cases = load_golden_dataset(dataset_path)
    documents = load_text_documents(args.documents_dir)
    adapter = None
    try:
        adapter, summary = build_configured_retrieval_adapter(
            documents,
            provider=provider,
            collection_name=args.collection_name,
            persist_directory=args.persist_directory,
            score_threshold=args.score_threshold,
        )
        case_top_k_values = sorted({case.top_k for case in cases})
        report = EvaluationRunner(
            adapter,
            dataset_name=f"{provider}-retrieval-baseline",
            default_top_k=settings.retrieval_top_k,
            metadata={
                **summary.to_dict(),
                "case_count": len(cases),
                "case_top_k_values": case_top_k_values,
                "score_threshold": args.score_threshold,
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
    report_stem = _default_report_stem(provider, args.score_threshold)
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
