"""Data models shared by the offline evaluation runner and reports."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


def _unique_strings(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise TypeError(f"{field_name} 必须是字符串列表")
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} 只能包含非空字符串")
        item = value.strip()
        if item not in normalized:
            normalized.append(item)
    return tuple(normalized)


@dataclass(frozen=True)
class GoldenCase:
    """One question and its expected retrieval/answer behavior."""

    id: str
    question: str
    expected_document_ids: tuple[str, ...] = field(default_factory=tuple)
    expected_keywords: tuple[str, ...] = field(default_factory=tuple)
    should_answer: bool = True
    top_k: int = 3

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("评估用例 id 不能为空")
        if not isinstance(self.question, str) or not self.question.strip():
            raise ValueError("评估问题不能为空")
        if not isinstance(self.should_answer, bool):
            raise TypeError("should_answer 必须是布尔值")
        if not isinstance(self.top_k, int) or isinstance(self.top_k, bool) or self.top_k <= 0:
            raise ValueError("top_k 必须是正整数")
        object.__setattr__(
            self,
            "id",
            self.id.strip(),
        )
        object.__setattr__(self, "question", self.question.strip())
        object.__setattr__(
            self,
            "expected_document_ids",
            _unique_strings(self.expected_document_ids, "expected_document_ids"),
        )
        object.__setattr__(
            self,
            "expected_keywords",
            _unique_strings(self.expected_keywords, "expected_keywords"),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "GoldenCase":
        if not isinstance(payload, Mapping):
            raise TypeError("黄金评估用例必须是 JSON 对象")
        allowed = {
            "id",
            "question",
            "expected_document_ids",
            "expected_keywords",
            "should_answer",
            "top_k",
        }
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ValueError(f"黄金评估用例包含未知字段: {', '.join(unknown)}")
        return cls(
            id=payload.get("id", ""),
            question=payload.get("question", ""),
            expected_document_ids=tuple(payload.get("expected_document_ids", ())),
            expected_keywords=tuple(payload.get("expected_keywords", ())),
            should_answer=payload.get("should_answer", True),
            top_k=payload.get("top_k", 3),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "expected_document_ids": list(self.expected_document_ids),
            "expected_keywords": list(self.expected_keywords),
            "should_answer": self.should_answer,
            "top_k": self.top_k,
        }


@dataclass(frozen=True)
class RetrievedDocument:
    """Minimal adapter-neutral representation of a retrieved chunk."""

    document_id: str
    content: str = ""
    chunk_id: str = ""
    rank: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)
    distance: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.document_id, str) or not self.document_id.strip():
            raise ValueError("RetrievedDocument.document_id 不能为空")
        if self.rank < 0:
            raise ValueError("RetrievedDocument.rank 不能小于 0")
        object.__setattr__(self, "document_id", self.document_id.strip())
        object.__setattr__(self, "chunk_id", str(self.chunk_id or ""))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))
        if self.distance is not None:
            object.__setattr__(self, "distance", float(self.distance))

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "content": self.content,
            "chunk_id": self.chunk_id,
            "rank": self.rank,
            "metadata": dict(self.metadata),
            "distance": self.distance,
        }


@dataclass(frozen=True)
class AnswerResult:
    """Answer adapter output used by refusal-accuracy evaluation."""

    answered: bool
    text: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.answered, bool):
            raise TypeError("AnswerResult.answered 必须是布尔值")


@dataclass(frozen=True)
class CaseEvaluation:
    """Evaluation result for one golden case."""

    case_id: str
    question: str
    top_k: int
    retrieved_document_ids: tuple[str, ...]
    retrieved_distances: tuple[float | None, ...]
    metrics: Mapping[str, float | None]
    duration_ms: float
    status: str = "success"
    answered: bool | None = None
    error_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "question": self.question,
            "top_k": self.top_k,
            "retrieved_document_ids": list(self.retrieved_document_ids),
            "retrieved_distances": list(self.retrieved_distances),
            "metrics": dict(self.metrics),
            "duration_ms": round(self.duration_ms, 3),
            "status": self.status,
            "answered": self.answered,
            "error_type": self.error_type,
        }


@dataclass(frozen=True)
class EvaluationReport:
    """Serializable aggregate report produced by :class:`EvaluationRunner`."""

    dataset_name: str
    top_k: int
    case_results: tuple[CaseEvaluation, ...]
    metrics: Mapping[str, float | None]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "top_k": self.top_k,
            "case_count": len(self.case_results),
            "metadata": dict(self.metadata),
            "metrics": dict(self.metrics),
            "cases": [result.to_dict() for result in self.case_results],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent) + "\n"

    def to_markdown(self) -> str:
        lines = [
            f"# RAG Evaluation Report: {self.dataset_name}",
            "",
            f"- Cases: {len(self.case_results)}",
            f"- Default Top-K: {self.top_k}",
        ]
        if self.metadata:
            lines.extend(["", "## Run Configuration", "", "| Setting | Value |", "|---|---|"])
            for name, value in self.metadata.items():
                formatted = json.dumps(value, ensure_ascii=False) if value is not None else "null"
                lines.append(f"| `{name}` | `{formatted}` |")
        lines.extend(["", "## Aggregate Metrics", "", "| Metric | Value |", "|---|---:|"])
        for name, value in self.metrics.items():
            formatted = "N/A" if value is None else f"{value:.4f}"
            lines.append(f"| `{name}` | {formatted} |")
        lines.extend(["", "## Cases", "", "| Case | Status | Top-K | Duration (ms) |", "|---|---|---:|---:|"])
        for result in self.case_results:
            lines.append(
                f"| `{result.case_id}` | {result.status} | {result.top_k} | "
                f"{result.duration_ms:.3f} |"
            )
        return "\n".join(lines) + "\n"
