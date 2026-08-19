"""End-to-end answer quality evaluation runner and real-provider CLI."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Mapping, Sequence
from math import isfinite
from pathlib import Path
from time import perf_counter
from typing import Any

from app.config import settings
from app.core.generator import UniversalLLMClient
from evaluation.adapters import RetrievalAdapter
from evaluation.answer_adapters import (
    CITATION_PARSER_VERSION,
    AnswerGenerator,
    AnswerJudge,
    LLMAnswerGenerator,
    LLMAnswerJudge,
    parse_answer_citations,
)
from evaluation.answer_metrics import aggregate_answer_evaluations
from evaluation.answer_models import (
    REFUSAL_TEXT,
    AnswerCaseEvaluation,
    AnswerEvaluationReport,
    AnswerQualityCase,
    GeneratedAnswer,
    load_answer_quality_dataset,
)
from evaluation.answer_reports import validate_answer_report_paths, write_answer_reports
from evaluation.fingerprints import text_corpus_sha256, text_file_sha256, text_sha256
from evaluation.models import RetrievedDocument
from evaluation.production import (
    IndexingSummary,
    build_configured_hybrid_retrieval_adapter,
    build_configured_retrieval_adapter,
    build_lexical_retrieval_adapter,
    load_text_documents,
)


class AnswerEvaluationRunner:
    """Run every case independently so provider failures remain reportable."""

    def __init__(
        self,
        retrieval_adapter: RetrievalAdapter,
        generator: AnswerGenerator,
        judge: AnswerJudge,
        *,
        dataset_name: str,
        metadata: Mapping[str, Any],
    ):
        if not callable(getattr(retrieval_adapter, "retrieve", None)):
            raise TypeError("retrieval_adapter 必须实现 retrieve")
        if not isinstance(generator, AnswerGenerator):
            raise TypeError("generator 必须实现 AnswerGenerator")
        if not isinstance(judge, AnswerJudge):
            raise TypeError("judge 必须实现 AnswerJudge")
        if not isinstance(dataset_name, str) or not dataset_name.strip():
            raise ValueError("dataset_name 必须是非空字符串")
        if not isinstance(metadata, Mapping):
            raise TypeError("metadata 必须是对象")
        self.retrieval_adapter = retrieval_adapter
        self.generator = generator
        self.judge = judge
        self.dataset_name = dataset_name.strip()
        self.metadata = dict(metadata)

    @staticmethod
    def _duration_ms(started_at: float) -> float:
        return max(0.0, (perf_counter() - started_at) * 1000)

    @staticmethod
    def _error(
        case: AnswerQualityCase,
        *,
        stage: str,
        error: Exception,
        generated_answer: GeneratedAnswer | None = None,
    ) -> AnswerCaseEvaluation:
        return AnswerCaseEvaluation.error(
            case,
            error_stage=stage,
            error_type=type(error).__name__,
            generated_answer=generated_answer,
        )

    def _evaluate_case(self, case: AnswerQualityCase) -> AnswerCaseEvaluation:
        retrieval_started = perf_counter()
        try:
            retrieved = self.retrieval_adapter.retrieve(case.question, case.top_k)
            if isinstance(retrieved, (str, bytes)) or not isinstance(
                retrieved, Sequence
            ):
                raise TypeError("检索结果必须是 RetrievedDocument 列表")
            documents = tuple(retrieved)
            if any(not isinstance(item, RetrievedDocument) for item in documents):
                raise TypeError("检索结果只能包含 RetrievedDocument")
            retrieval_duration_ms = self._duration_ms(retrieval_started)
        except Exception as exc:
            return self._error(case, stage="retrieval", error=exc)

        if not documents:
            return AnswerCaseEvaluation.success(
                case,
                GeneratedAnswer.no_context(retrieval_duration_ms=retrieval_duration_ms),
            )

        generation_started = perf_counter()
        text = ""
        try:
            text = self.generator.generate(case, documents)
            generation_duration_ms = self._duration_ms(generation_started)
            citations = parse_answer_citations(text)
            generated_answer = GeneratedAnswer.from_generation(
                text,
                documents,
                citations=citations,
                retrieval_duration_ms=retrieval_duration_ms,
                generation_duration_ms=generation_duration_ms,
            )
        except Exception as exc:
            generation_duration_ms = self._duration_ms(generation_started)
            generated_error = GeneratedAnswer.error(
                retrieved_documents=documents,
                text=text if isinstance(text, str) else "",
                retrieval_duration_ms=retrieval_duration_ms,
                generation_duration_ms=generation_duration_ms,
            )
            return self._error(
                case,
                stage="generation",
                error=exc,
                generated_answer=generated_error,
            )

        if not case.should_answer or generated_answer.outcome != "answered":
            return AnswerCaseEvaluation.success(case, generated_answer)

        try:
            judge_result = self.judge.judge(case, generated_answer)
        except Exception as exc:
            return self._error(
                case,
                stage="judge",
                error=exc,
                generated_answer=generated_answer,
            )
        return AnswerCaseEvaluation.success(
            case,
            generated_answer,
            judge_result=judge_result,
        )

    def run(
        self,
        cases: Sequence[AnswerQualityCase],
        *,
        generated_at: str | None = None,
    ) -> AnswerEvaluationReport:
        if isinstance(cases, (str, bytes)) or not isinstance(cases, Sequence):
            raise TypeError("cases 必须是 AnswerQualityCase 列表")
        normalized_cases = tuple(cases)
        if not normalized_cases:
            raise ValueError("cases 不能为空")
        if any(not isinstance(case, AnswerQualityCase) for case in normalized_cases):
            raise TypeError("cases 只能包含 AnswerQualityCase")
        results = tuple(self._evaluate_case(case) for case in normalized_cases)
        return aggregate_answer_evaluations(
            results,
            dataset_name=self.dataset_name,
            metadata=self.metadata,
            generated_at=generated_at,
        )


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("必须是正整数")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if not isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("必须是正数")
    return parsed


def _nonnegative_float(value: str) -> float:
    parsed = float(value)
    if not isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("必须是非负数")
    return parsed


def _temperature(value: str) -> float:
    parsed = float(value)
    if not isfinite(parsed) or not 0 <= parsed <= 2:
        raise argparse.ArgumentTypeError("必须在 0 到 2 之间")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run answer quality evaluation with real retrieval and LLM providers"
    )
    parser.add_argument("--dataset", required=True)
    parser.add_argument(
        "--documents-dir",
        default=None,
        help="TXT directory; defaults to DATASET parent/documents",
    )
    parser.add_argument("--dataset-name", default=None)
    parser.add_argument(
        "--embedding-provider",
        default=None,
        help="Defaults to DEFAULT_EMBEDDING_PROVIDER",
    )
    parser.add_argument(
        "--retrieval-mode",
        choices=("dense", "bm25", "hybrid"),
        default="dense",
    )
    parser.add_argument("--collection-name", default="rag_answer_evaluation")
    parser.add_argument("--score-threshold", type=_nonnegative_float, default=None)
    parser.add_argument(
        "--lexical-score-threshold",
        type=_nonnegative_float,
        default=None,
    )
    parser.add_argument("--dense-weight", type=_positive_float, default=1.0)
    parser.add_argument("--lexical-weight", type=_positive_float, default=1.0)
    parser.add_argument("--rrf-k", type=_positive_int, default=60)
    parser.add_argument("--candidate-multiplier", type=_positive_int, default=5)
    parser.add_argument("--generator-provider", default=None)
    parser.add_argument("--generator-model", default=None)
    parser.add_argument(
        "--generator-temperature",
        type=_temperature,
        default=settings.llm_temperature,
    )
    parser.add_argument(
        "--generator-max-tokens",
        type=_positive_int,
        default=settings.llm_max_tokens,
    )
    parser.add_argument(
        "--generator-request-timeout", type=_positive_float, default=60.0
    )
    parser.add_argument("--judge-provider", default=None)
    parser.add_argument("--judge-model", default=None)
    parser.add_argument("--judge-temperature", type=_temperature, default=0.0)
    parser.add_argument("--judge-max-tokens", type=_positive_int, default=1000)
    parser.add_argument("--judge-request-timeout", type=_positive_float, default=60.0)
    parser.add_argument("--milvus-uri", default=settings.milvus_uri)
    parser.add_argument("--milvus-token", default=settings.milvus_token)
    parser.add_argument("--milvus-db-name", default=settings.milvus_db_name)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-markdown", required=True)
    return parser


def _git_state() -> tuple[str | None, bool]:
    try:
        commit_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        status_result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None, True
    commit = commit_result.stdout.strip() or None
    return commit, bool(status_result.stdout.strip())


def _build_retrieval(
    args: argparse.Namespace,
    documents: Sequence[Any],
) -> tuple[RetrievalAdapter, IndexingSummary]:
    provider = args.embedding_provider or settings.default_embedding_provider
    if args.retrieval_mode == "dense":
        return build_configured_retrieval_adapter(
            documents,
            provider=provider,
            collection_name=args.collection_name,
            milvus_uri=args.milvus_uri,
            milvus_token=args.milvus_token,
            milvus_db_name=args.milvus_db_name,
            score_threshold=args.score_threshold,
        )
    if args.retrieval_mode == "bm25":
        return build_lexical_retrieval_adapter(
            documents,
            lexical_score_threshold=args.lexical_score_threshold,
        )
    return build_configured_hybrid_retrieval_adapter(
        documents,
        provider=provider,
        collection_name=args.collection_name,
        milvus_uri=args.milvus_uri,
        milvus_token=args.milvus_token,
        milvus_db_name=args.milvus_db_name,
        score_threshold=args.score_threshold,
        lexical_score_threshold=args.lexical_score_threshold,
        dense_weight=args.dense_weight,
        lexical_weight=args.lexical_weight,
        rrf_k=args.rrf_k,
        candidate_multiplier=args.candidate_multiplier,
    )


def _build_generator(args: argparse.Namespace) -> LLMAnswerGenerator:
    client = UniversalLLMClient(
        provider=args.generator_provider or settings.default_llm_provider,
        model=args.generator_model,
        request_timeout_seconds=args.generator_request_timeout,
    )
    return LLMAnswerGenerator(
        client,
        temperature=args.generator_temperature,
        max_tokens=args.generator_max_tokens,
    )


def _build_judge(args: argparse.Namespace) -> LLMAnswerJudge:
    client = UniversalLLMClient(
        provider=args.judge_provider or settings.default_llm_provider,
        model=args.judge_model,
        request_timeout_seconds=args.judge_request_timeout,
    )
    return LLMAnswerJudge(
        client,
        temperature=args.judge_temperature,
        max_tokens=args.judge_max_tokens,
    )


def _report_metadata(
    args: argparse.Namespace,
    *,
    dataset_path: Path,
    documents_directory: Path,
    cases: Sequence[AnswerQualityCase],
    summary: IndexingSummary,
    generator: LLMAnswerGenerator,
    judge: LLMAnswerJudge,
) -> dict[str, Any]:
    git_commit, dirty = _git_state()
    return {
        "git_commit": git_commit,
        "dirty": dirty,
        "dataset_sha256": text_file_sha256(dataset_path),
        "documents_sha256": text_corpus_sha256(documents_directory),
        "embedding_provider": summary.embedding_provider,
        "embedding_model": summary.embedding_model,
        "embedding_dimension": summary.embedding_dimension,
        "chunk_size": summary.chunk_size,
        "chunk_overlap": summary.chunk_overlap,
        "retrieval_mode": args.retrieval_mode,
        "top_k": sorted({case.top_k for case in cases}),
        "score_threshold": args.score_threshold,
        "generator_provider": generator.provider,
        "generator_model": generator.model,
        "generator_temperature": generator.config.temperature,
        "generator_max_tokens": generator.config.max_tokens,
        "generator_prompt_sha256": generator.prompt_sha256,
        "judge_provider": judge.provider,
        "judge_model": judge.model,
        "judge_temperature": judge.config.temperature,
        "judge_max_tokens": judge.config.max_tokens,
        "judge_prompt_sha256": judge.prompt_sha256,
        "refusal_text_sha256": text_sha256(REFUSAL_TEXT),
        "citation_parser_version": CITATION_PARSER_VERSION,
        "dataset_path": dataset_path.as_posix(),
        "documents_directory": documents_directory.as_posix(),
        "collection_name": args.collection_name,
        "lexical_score_threshold": args.lexical_score_threshold,
        "dense_weight": args.dense_weight,
        "lexical_weight": args.lexical_weight,
        "rrf_k": args.rrf_k,
        "candidate_multiplier": args.candidate_multiplier,
    }


def _run(args: argparse.Namespace) -> int:
    validate_answer_report_paths(args.output_json, args.output_markdown)
    dataset_path = Path(args.dataset)
    documents_directory = Path(args.documents_dir or dataset_path.parent / "documents")
    cases = load_answer_quality_dataset(
        dataset_path,
        documents_directory=documents_directory,
    )
    documents = load_text_documents(documents_directory)
    retrieval_adapter: RetrievalAdapter | None = None
    try:
        retrieval_adapter, summary = _build_retrieval(args, documents)
        generator = _build_generator(args)
        judge = _build_judge(args)
        metadata = _report_metadata(
            args,
            dataset_path=dataset_path,
            documents_directory=documents_directory,
            cases=cases,
            summary=summary,
            generator=generator,
            judge=judge,
        )
        report = AnswerEvaluationRunner(
            retrieval_adapter,
            generator,
            judge,
            dataset_name=args.dataset_name or dataset_path.stem,
            metadata=metadata,
        ).run(cases)
    finally:
        if retrieval_adapter is not None:
            retrieval_adapter.close()

    json_path, markdown_path = write_answer_reports(
        report,
        args.output_json,
        args.output_markdown,
    )
    error_count = sum(result.status == "error" for result in report.case_results)
    print(f"answer_report_json={json_path}")
    print(f"answer_report_markdown={markdown_path}")
    print(f"case_count={len(report.case_results)}")
    print(f"error_count={error_count}")
    for name, value in report.metrics.items():
        print(f"metric.{name}={value}")
        print(f"metric_case_count.{name}={report.metric_case_counts[name]}")
    return 1 if error_count else 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _run(args)
    except Exception as exc:
        message = " ".join(str(exc).splitlines())
        print(
            f"answer_evaluation_error={type(exc).__name__}: {message}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
