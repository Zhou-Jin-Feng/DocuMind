"""Strict data contracts for end-to-end answer quality evaluation."""

from __future__ import annotations

import html
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path
from typing import Any, Literal

from evaluation.models import RetrievedDocument

ANSWER_EVALUATION_SCHEMA_VERSION = 1
REFUSAL_TEXT = "根据提供的文档，未找到相关信息。"
ANSWER_OUTCOMES = ("answered", "refused", "no_context", "error")
ANSWER_CASE_STATUSES = ("success", "error")
ANSWER_SPLITS = ("train", "validation", "holdout")
JUDGE_SCORE_FIELDS = (
    "faithfulness",
    "citation_correctness",
    "citation_completeness",
    "answer_relevance",
)
ANSWER_METRIC_NAMES = (
    "successful_case_rate",
    "refusal_accuracy",
    *JUDGE_SCORE_FIELDS,
)
REQUIRED_REPORT_METADATA_FIELDS = frozenset(
    {
        "git_commit",
        "dirty",
        "dataset_sha256",
        "documents_sha256",
        "embedding_provider",
        "embedding_model",
        "embedding_dimension",
        "chunk_size",
        "chunk_overlap",
        "retrieval_mode",
        "top_k",
        "score_threshold",
        "generator_provider",
        "generator_model",
        "generator_temperature",
        "generator_max_tokens",
        "generator_prompt_sha256",
        "judge_provider",
        "judge_model",
        "judge_temperature",
        "judge_max_tokens",
        "judge_prompt_sha256",
        "refusal_text_sha256",
        "citation_parser_version",
    }
)

AnswerOutcome = Literal["answered", "refused", "no_context", "error"]
AnswerCaseStatus = Literal["success", "error"]


def _reject_duplicate_json_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON 存在重复字段: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"JSON 不允许非有限数: {value}")


def _parse_strict_json_object(raw: str, *, context: str) -> Mapping[str, Any]:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{context} 不能为空")
    try:
        payload = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"{context} 不是严格 JSON: {exc.msg}") from None
    if not isinstance(payload, Mapping):
        raise TypeError(f"{context} 顶层必须是 JSON 对象")
    return payload


def _require_exact_fields(
    payload: Mapping[str, Any], expected: set[str], *, context: str
) -> None:
    actual = set(payload)
    if actual == expected:
        return
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    raise ValueError(f"{context} 字段不匹配: missing={missing}, unknown={unknown}")


def _nonempty_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空字符串")
    return value.strip()


def _string_tuple(
    values: Sequence[str],
    field_name: str,
    *,
    allow_empty: bool = True,
    reject_duplicates: bool = True,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} 必须是字符串列表")
    normalized: list[str] = []
    for value in values:
        item = _nonempty_text(value, field_name)
        if reject_duplicates and item in normalized:
            raise ValueError(f"{field_name} 不能包含重复值: {item}")
        normalized.append(item)
    if not allow_empty and not normalized:
        raise ValueError(f"{field_name} 不能为空")
    return tuple(normalized)


def _nonnegative_duration(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} 必须是数字")
    numeric = float(value)
    if not isfinite(numeric) or numeric < 0:
        raise ValueError(f"{field_name} 必须是非负有限数")
    return numeric


@dataclass(frozen=True, slots=True)
class AnswerQualityCase:
    """One strict golden case for answer-level evaluation."""

    id: str
    question: str
    expected_document_ids: tuple[str, ...]
    should_answer: bool
    reference_answer: str
    reference_claims: tuple[str, ...]
    category: str
    split: str
    top_k: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _nonempty_text(self.id, "id"))
        object.__setattr__(self, "question", _nonempty_text(self.question, "question"))
        if not isinstance(self.should_answer, bool):
            raise TypeError("should_answer 必须是布尔值")
        if (
            isinstance(self.top_k, bool)
            or not isinstance(self.top_k, int)
            or self.top_k <= 0
        ):
            raise ValueError("top_k 必须是正整数")

        category = _nonempty_text(self.category, "category").casefold()
        split = _nonempty_text(self.split, "split").casefold()
        if split not in ANSWER_SPLITS:
            raise ValueError("split 必须是 train/validation/holdout")
        document_ids = _string_tuple(
            self.expected_document_ids, "expected_document_ids"
        )
        claims = _string_tuple(self.reference_claims, "reference_claims")
        if not isinstance(self.reference_answer, str):
            raise TypeError("reference_answer 必须是字符串")
        reference_answer = self.reference_answer.strip()

        if self.should_answer:
            if not document_ids:
                raise ValueError("should_answer=true 时 expected_document_ids 不能为空")
            if not reference_answer:
                raise ValueError("should_answer=true 时 reference_answer 不能为空")
            if not claims:
                raise ValueError("should_answer=true 时 reference_claims 不能为空")
        elif reference_answer or claims:
            raise ValueError(
                "should_answer=false 时 reference_answer 和 reference_claims 必须为空"
            )

        object.__setattr__(self, "category", category)
        object.__setattr__(self, "split", split)
        object.__setattr__(self, "expected_document_ids", document_ids)
        object.__setattr__(self, "reference_answer", reference_answer)
        object.__setattr__(self, "reference_claims", claims)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AnswerQualityCase":
        if not isinstance(payload, Mapping):
            raise TypeError("答案质量用例必须是 JSON 对象")
        expected = {
            "id",
            "question",
            "expected_document_ids",
            "should_answer",
            "reference_answer",
            "reference_claims",
            "category",
            "split",
            "top_k",
        }
        _require_exact_fields(payload, expected, context="答案质量用例")
        return cls(
            id=payload["id"],
            question=payload["question"],
            expected_document_ids=payload["expected_document_ids"],
            should_answer=payload["should_answer"],
            reference_answer=payload["reference_answer"],
            reference_claims=payload["reference_claims"],
            category=payload["category"],
            split=payload["split"],
            top_k=payload["top_k"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "expected_document_ids": list(self.expected_document_ids),
            "should_answer": self.should_answer,
            "reference_answer": self.reference_answer,
            "reference_claims": list(self.reference_claims),
            "category": self.category,
            "split": self.split,
            "top_k": self.top_k,
        }


def load_answer_quality_dataset(
    path: str | Path, *, documents_directory: str | Path | None = None
) -> tuple[AnswerQualityCase, ...]:
    """Load strict JSONL cases and verify every referenced TXT fixture."""

    dataset_path = Path(path)
    if not dataset_path.is_file():
        raise FileNotFoundError(f"答案评测数据集不存在: {dataset_path}")
    try:
        text = dataset_path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"答案评测数据集不是有效 UTF-8: {dataset_path}") from exc

    cases: list[AnswerQualityCase] = []
    seen_ids: set[str] = set()
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        if not raw_line.strip():
            continue
        payload = _parse_strict_json_object(
            raw_line, context=f"答案评测数据集第 {line_number} 行"
        )
        case = AnswerQualityCase.from_dict(payload)
        normalized_id = case.id.casefold()
        if normalized_id in seen_ids:
            raise ValueError(f"答案评测用例 id 重复: {case.id}")
        seen_ids.add(normalized_id)
        cases.append(case)
    if not cases:
        raise ValueError("答案评测数据集不能为空")

    document_root = (
        Path(documents_directory)
        if documents_directory is not None
        else dataset_path.parent / "documents"
    )
    if not document_root.is_dir():
        raise NotADirectoryError(f"答案评测文档目录不存在: {document_root}")
    document_paths = sorted(document_root.glob("*.txt"), key=lambda item: item.name)
    if not document_paths:
        raise ValueError(f"答案评测文档目录没有 TXT 文件: {document_root}")
    document_ids = {document_path.stem for document_path in document_paths}
    if len({document_id.casefold() for document_id in document_ids}) != len(
        document_ids
    ):
        raise ValueError("答案评测文档 ID 在忽略大小写后重复")
    for case in cases:
        unknown = sorted(set(case.expected_document_ids) - document_ids)
        if unknown:
            raise ValueError(f"答案评测用例 {case.id} 引用未知文档 ID: {unknown}")
    return tuple(cases)


@dataclass(frozen=True, slots=True)
class GeneratedAnswer:
    """Generator output plus deterministic outcome and retrieval evidence."""

    text: str
    outcome: AnswerOutcome
    retrieved_documents: tuple[RetrievedDocument, ...] = field(default_factory=tuple)
    citations: tuple[int, ...] = field(default_factory=tuple)
    retrieval_duration_ms: float = 0.0
    generation_duration_ms: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError("GeneratedAnswer.text 必须是字符串")
        if self.outcome not in ANSWER_OUTCOMES:
            raise ValueError(f"GeneratedAnswer.outcome 非法: {self.outcome}")
        if isinstance(self.retrieved_documents, (str, bytes)) or not isinstance(
            self.retrieved_documents, Sequence
        ):
            raise TypeError("retrieved_documents 必须是 RetrievedDocument 列表")
        documents = tuple(self.retrieved_documents)
        if any(not isinstance(item, RetrievedDocument) for item in documents):
            raise TypeError("retrieved_documents 只能包含 RetrievedDocument")
        if isinstance(self.citations, (str, bytes)) or not isinstance(
            self.citations, Sequence
        ):
            raise TypeError("citations 必须是正整数列表")
        citations: list[int] = []
        for citation in self.citations:
            if (
                isinstance(citation, bool)
                or not isinstance(citation, int)
                or citation <= 0
            ):
                raise ValueError("citations 只能包含正整数")
            citations.append(citation)

        normalized_text = self.text.strip()
        if self.outcome == "answered" and (
            not normalized_text or normalized_text == REFUSAL_TEXT
        ):
            raise ValueError("answered 必须包含非拒答文本")
        if self.outcome == "refused" and normalized_text != REFUSAL_TEXT:
            raise ValueError("refused 必须精确使用统一拒答文本")
        if self.outcome == "no_context" and (documents or normalized_text):
            raise ValueError("no_context 不能包含检索文档或生成文本")

        object.__setattr__(self, "text", normalized_text)
        object.__setattr__(self, "retrieved_documents", documents)
        object.__setattr__(self, "citations", tuple(citations))
        object.__setattr__(
            self,
            "retrieval_duration_ms",
            _nonnegative_duration(self.retrieval_duration_ms, "retrieval_duration_ms"),
        )
        object.__setattr__(
            self,
            "generation_duration_ms",
            _nonnegative_duration(
                self.generation_duration_ms, "generation_duration_ms"
            ),
        )

    @classmethod
    def from_generation(
        cls,
        text: str,
        retrieved_documents: Sequence[RetrievedDocument],
        *,
        citations: Sequence[int] = (),
        retrieval_duration_ms: float = 0.0,
        generation_duration_ms: float = 0.0,
    ) -> "GeneratedAnswer":
        documents = tuple(retrieved_documents)
        if not documents:
            if isinstance(text, str) and text.strip():
                raise ValueError("无上下文时不应调用生成器")
            return cls.no_context(retrieval_duration_ms=retrieval_duration_ms)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("生成器返回空文本")
        normalized_text = text.strip()
        outcome: AnswerOutcome = (
            "refused" if normalized_text == REFUSAL_TEXT else "answered"
        )
        return cls(
            text=normalized_text,
            outcome=outcome,
            retrieved_documents=documents,
            citations=tuple(citations),
            retrieval_duration_ms=retrieval_duration_ms,
            generation_duration_ms=generation_duration_ms,
        )

    @classmethod
    def no_context(cls, *, retrieval_duration_ms: float = 0.0) -> "GeneratedAnswer":
        return cls(
            text="",
            outcome="no_context",
            retrieval_duration_ms=retrieval_duration_ms,
        )

    @classmethod
    def error(
        cls,
        *,
        retrieved_documents: Sequence[RetrievedDocument] = (),
        text: str = "",
        retrieval_duration_ms: float = 0.0,
        generation_duration_ms: float = 0.0,
    ) -> "GeneratedAnswer":
        return cls(
            text=text,
            outcome="error",
            retrieved_documents=tuple(retrieved_documents),
            retrieval_duration_ms=retrieval_duration_ms,
            generation_duration_ms=generation_duration_ms,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "outcome": self.outcome,
            "retrieved_documents": [
                document.to_dict() for document in self.retrieved_documents
            ],
            "citations": list(self.citations),
            "retrieval_duration_ms": self.retrieval_duration_ms,
            "generation_duration_ms": self.generation_duration_ms,
        }


@dataclass(frozen=True, slots=True)
class JudgeResult:
    """Strict, validated semantic scores returned by an answer judge."""

    faithfulness: float
    citation_correctness: float
    citation_completeness: float
    answer_relevance: float
    unsupported_claims: tuple[str, ...]
    invalid_citations: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        for field_name in JUDGE_SCORE_FIELDS:
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"JudgeResult.{field_name} 必须是数字")
            numeric = float(value)
            if not isfinite(numeric) or not 0 <= numeric <= 1:
                raise ValueError(f"JudgeResult.{field_name} 必须是 0 到 1 的有限数")
            object.__setattr__(self, field_name, numeric)
        object.__setattr__(
            self,
            "unsupported_claims",
            _string_tuple(
                self.unsupported_claims,
                "unsupported_claims",
                reject_duplicates=False,
            ),
        )
        object.__setattr__(
            self,
            "invalid_citations",
            _string_tuple(
                self.invalid_citations,
                "invalid_citations",
                reject_duplicates=False,
            ),
        )
        if not isinstance(self.reason, str):
            raise TypeError("JudgeResult.reason 必须是字符串")
        object.__setattr__(self, "reason", self.reason.strip())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "JudgeResult":
        if not isinstance(payload, Mapping):
            raise TypeError("Judge 结果必须是 JSON 对象")
        expected = {
            *JUDGE_SCORE_FIELDS,
            "unsupported_claims",
            "invalid_citations",
            "reason",
        }
        _require_exact_fields(payload, expected, context="Judge 结果")
        return cls(
            faithfulness=payload["faithfulness"],
            citation_correctness=payload["citation_correctness"],
            citation_completeness=payload["citation_completeness"],
            answer_relevance=payload["answer_relevance"],
            unsupported_claims=payload["unsupported_claims"],
            invalid_citations=payload["invalid_citations"],
            reason=payload["reason"],
        )

    @classmethod
    def from_json(cls, raw: str) -> "JudgeResult":
        return cls.from_dict(_parse_strict_json_object(raw, context="Judge 输出"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "faithfulness": self.faithfulness,
            "citation_correctness": self.citation_correctness,
            "citation_completeness": self.citation_completeness,
            "answer_relevance": self.answer_relevance,
            "unsupported_claims": list(self.unsupported_claims),
            "invalid_citations": list(self.invalid_citations),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class AnswerCaseEvaluation:
    """Serializable outcome for one answer quality case."""

    case_id: str
    question: str
    should_answer: bool
    category: str
    split: str
    status: AnswerCaseStatus
    generated_answer: GeneratedAnswer | None = None
    judge_result: JudgeResult | None = None
    error_stage: str | None = None
    error_type: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _nonempty_text(self.case_id, "case_id"))
        object.__setattr__(self, "question", _nonempty_text(self.question, "question"))
        if not isinstance(self.should_answer, bool):
            raise TypeError("should_answer 必须是布尔值")
        object.__setattr__(
            self, "category", _nonempty_text(self.category, "category").casefold()
        )
        split = _nonempty_text(self.split, "split").casefold()
        if split not in ANSWER_SPLITS:
            raise ValueError("split 必须是 train/validation/holdout")
        object.__setattr__(self, "split", split)
        if self.status not in ANSWER_CASE_STATUSES:
            raise ValueError(f"答案评测案例 status 非法: {self.status}")
        if self.generated_answer is not None and not isinstance(
            self.generated_answer, GeneratedAnswer
        ):
            raise TypeError("generated_answer 必须是 GeneratedAnswer 或 None")
        if self.judge_result is not None and not isinstance(
            self.judge_result, JudgeResult
        ):
            raise TypeError("judge_result 必须是 JudgeResult 或 None")

        if self.status == "success":
            if (
                self.generated_answer is None
                or self.generated_answer.outcome == "error"
            ):
                raise ValueError("success 案例必须包含非 error 的生成结果")
            if self.error_stage is not None or self.error_type is not None:
                raise ValueError("success 案例不能记录错误阶段或类型")
            judge_required = (
                self.should_answer and self.generated_answer.outcome == "answered"
            )
            if judge_required != (self.judge_result is not None):
                raise ValueError(
                    "Judge 结果只能且必须用于 should_answer=true 且 outcome=answered 的成功案例"
                )
        else:
            if not isinstance(self.error_stage, str) or not self.error_stage.strip():
                raise ValueError("error 案例必须记录 error_stage")
            if not isinstance(self.error_type, str) or not self.error_type.strip():
                raise ValueError("error 案例必须记录 error_type")
            if self.judge_result is not None:
                raise ValueError("error 案例不能包含 Judge 分数")
            object.__setattr__(self, "error_stage", self.error_stage.strip())
            object.__setattr__(self, "error_type", self.error_type.strip())

    @classmethod
    def success(
        cls,
        case: AnswerQualityCase,
        generated_answer: GeneratedAnswer,
        *,
        judge_result: JudgeResult | None = None,
    ) -> "AnswerCaseEvaluation":
        return cls(
            case_id=case.id,
            question=case.question,
            should_answer=case.should_answer,
            category=case.category,
            split=case.split,
            status="success",
            generated_answer=generated_answer,
            judge_result=judge_result,
        )

    @classmethod
    def error(
        cls,
        case: AnswerQualityCase,
        *,
        error_stage: str,
        error_type: str,
        generated_answer: GeneratedAnswer | None = None,
    ) -> "AnswerCaseEvaluation":
        return cls(
            case_id=case.id,
            question=case.question,
            should_answer=case.should_answer,
            category=case.category,
            split=case.split,
            status="error",
            generated_answer=generated_answer,
            error_stage=error_stage,
            error_type=error_type,
        )

    @property
    def refusal_correct(self) -> bool | None:
        if self.status != "success" or self.generated_answer is None:
            return None
        return (self.generated_answer.outcome == "answered") == self.should_answer

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "question": self.question,
            "should_answer": self.should_answer,
            "category": self.category,
            "split": self.split,
            "status": self.status,
            "generated_answer": (
                self.generated_answer.to_dict()
                if self.generated_answer is not None
                else None
            ),
            "judge_result": (
                self.judge_result.to_dict() if self.judge_result is not None else None
            ),
            "refusal_correct": self.refusal_correct,
            "error_stage": self.error_stage,
            "error_type": self.error_type,
        }


@dataclass(frozen=True, slots=True)
class AnswerEvaluationReport:
    """Independent report contract for answer-level evaluation."""

    schema_version: int
    dataset_name: str
    generated_at: str
    case_results: tuple[AnswerCaseEvaluation, ...]
    metadata: Mapping[str, Any]
    metrics: Mapping[str, float | None]
    metric_case_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        if self.schema_version != ANSWER_EVALUATION_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version 必须是 {ANSWER_EVALUATION_SCHEMA_VERSION}"
            )
        object.__setattr__(
            self, "dataset_name", _nonempty_text(self.dataset_name, "dataset_name")
        )
        object.__setattr__(
            self, "generated_at", _nonempty_text(self.generated_at, "generated_at")
        )
        if isinstance(self.case_results, (str, bytes)) or not isinstance(
            self.case_results, Sequence
        ):
            raise TypeError("case_results 必须是 AnswerCaseEvaluation 列表")
        case_results = tuple(self.case_results)
        if not case_results:
            raise ValueError("case_results 不能为空")
        if any(not isinstance(item, AnswerCaseEvaluation) for item in case_results):
            raise TypeError("case_results 只能包含 AnswerCaseEvaluation")
        case_ids = [item.case_id.casefold() for item in case_results]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case_results 包含重复 case_id")

        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata 必须是对象")
        metadata = dict(self.metadata)
        missing_metadata = sorted(REQUIRED_REPORT_METADATA_FIELDS - set(metadata))
        if missing_metadata:
            raise ValueError(f"metadata 缺少必需字段: {missing_metadata}")
        if not isinstance(metadata["dirty"], bool):
            raise TypeError("metadata.dirty 必须是布尔值")

        if not isinstance(self.metrics, Mapping) or set(self.metrics) != set(
            ANSWER_METRIC_NAMES
        ):
            raise ValueError("metrics 必须完整包含固定的答案质量指标")
        metrics: dict[str, float | None] = {}
        for name in ANSWER_METRIC_NAMES:
            value = self.metrics[name]
            if value is None:
                metrics[name] = None
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"metrics.{name} 必须是数字或 null")
            numeric = float(value)
            if not isfinite(numeric) or not 0 <= numeric <= 1:
                raise ValueError(f"metrics.{name} 必须是 0 到 1 的有限数")
            metrics[name] = numeric

        if not isinstance(self.metric_case_counts, Mapping) or set(
            self.metric_case_counts
        ) != set(ANSWER_METRIC_NAMES):
            raise ValueError("metric_case_counts 必须与 metrics 字段完全一致")
        counts: dict[str, int] = {}
        for name in ANSWER_METRIC_NAMES:
            count = self.metric_case_counts[name]
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError(f"metric_case_counts.{name} 必须是非负整数")
            if count > len(case_results):
                raise ValueError(f"metric_case_counts.{name} 不能超过案例数")
            if count == 0 and metrics[name] is not None:
                raise ValueError(f"metric_case_counts.{name}=0 时指标必须为 null")
            if count > 0 and metrics[name] is None:
                raise ValueError(f"metric_case_counts.{name}>0 时指标不能为 null")
            counts[name] = count

        object.__setattr__(self, "case_results", case_results)
        object.__setattr__(self, "metadata", metadata)
        object.__setattr__(self, "metrics", metrics)
        object.__setattr__(self, "metric_case_counts", counts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "case_count": len(self.case_results),
            "generated_at": self.generated_at,
            "metadata": dict(self.metadata),
            "metrics": dict(self.metrics),
            "metric_case_counts": dict(self.metric_case_counts),
            "cases": [result.to_dict() for result in self.case_results],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return (
            json.dumps(
                self.to_dict(),
                ensure_ascii=False,
                indent=indent,
                allow_nan=False,
            )
            + "\n"
        )

    def to_markdown(self) -> str:
        """Render a human-reviewable report without trusting model text as markup."""

        def table_cell(value: Any) -> str:
            if value is None:
                return "-"
            if isinstance(value, bool):
                return "true" if value else "false"
            if isinstance(value, float):
                return f"{value:.4f}"
            if isinstance(value, (list, tuple, dict)):
                value = json.dumps(value, ensure_ascii=False, sort_keys=True)
            escaped = html.escape(str(value)).replace("\n", "<br>")
            for token in ("\\", "|", "*", "_", "[", "]", "`"):
                escaped = escaped.replace(token, f"\\{token}")
            return escaped

        lines = [
            "# Answer Quality Evaluation Report",
            "",
            f"- Dataset: `{table_cell(self.dataset_name)}`",
            f"- Generated at: `{table_cell(self.generated_at)}`",
            f"- Cases: `{len(self.case_results)}`",
            "",
            "## Metrics",
            "",
            "| Metric | Score | Evaluated cases |",
            "|---|---:|---:|",
        ]
        for name in ANSWER_METRIC_NAMES:
            lines.append(
                f"| `{name}` | {table_cell(self.metrics[name])} | "
                f"{self.metric_case_counts[name]} |"
            )

        lines.extend(
            [
                "",
                "## Reproducibility Metadata",
                "",
                "| Field | Value |",
                "|---|---|",
            ]
        )
        for name in sorted(self.metadata):
            lines.append(f"| `{name}` | {table_cell(self.metadata[name])} |")

        lines.extend(
            [
                "",
                "## Cases",
                "",
                "| Case | Split | Category | Status | Outcome | Refusal correct | Error |",
                "|---|---|---|---|---|---|---|",
            ]
        )
        for result in self.case_results:
            generated = result.generated_answer
            error = (
                f"{result.error_stage}:{result.error_type}"
                if result.status == "error"
                else None
            )
            lines.append(
                f"| `{table_cell(result.case_id)}` | {table_cell(result.split)} | "
                f"{table_cell(result.category)} | {result.status} | "
                f"{table_cell(generated.outcome if generated else None)} | "
                f"{table_cell(result.refusal_correct)} | {table_cell(error)} |"
            )

        lines.extend(["", "## Case Details", ""])
        for result in self.case_results:
            generated = result.generated_answer
            lines.extend(
                [
                    f"### {table_cell(result.case_id)}",
                    "",
                    "**Question**",
                    "",
                    f"<pre>{html.escape(result.question)}</pre>",
                    "",
                ]
            )
            if generated is not None:
                lines.extend(
                    [
                        "**Generated answer**",
                        "",
                        f"<pre>{html.escape(generated.text)}</pre>",
                        "",
                        f"Citations: `{table_cell(list(generated.citations))}`",
                        "",
                        "**Retrieved documents**",
                        "",
                    ]
                )
                for index, document in enumerate(generated.retrieved_documents, 1):
                    lines.extend(
                        [
                            f"<details><summary>文档{index}: "
                            f"{html.escape(document.document_id)}</summary>",
                            "",
                            f"<pre>{html.escape(document.content)}</pre>",
                            "",
                            "</details>",
                            "",
                        ]
                    )
            if result.judge_result is not None:
                judge_json = json.dumps(
                    result.judge_result.to_dict(),
                    ensure_ascii=False,
                    indent=2,
                )
                lines.extend(
                    [
                        "**Judge result**",
                        "",
                        f"<pre>{html.escape(judge_json)}</pre>",
                        "",
                    ]
                )
            if result.status == "error":
                lines.extend(
                    [
                        f"Error: `{table_cell(result.error_stage)}` / "
                        f"`{table_cell(result.error_type)}`",
                        "",
                    ]
                )
        return "\n".join(lines).rstrip() + "\n"
