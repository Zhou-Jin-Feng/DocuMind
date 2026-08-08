"""Reproducible query-rewrite artifacts for offline retrieval evaluation."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.query_rewriter import MappingQueryRewriter, QueryRewriter
from evaluation.models import GoldenCase


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError("Rewrite artifact JSON cannot contain duplicate keys")
        payload[key] = value
    return payload


@dataclass(frozen=True)
class RewriteArtifact:
    provider: str
    model: str
    max_rewrites: int
    dataset_sha256: str
    rewrites: Mapping[str, tuple[str, ...]]

    def __post_init__(self) -> None:
        for name in ("provider", "model", "dataset_sha256"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"RewriteArtifact.{name} 不能为空")
            object.__setattr__(self, name, value.strip())
        if not isinstance(self.max_rewrites, int) or isinstance(
            self.max_rewrites, bool
        ) or self.max_rewrites <= 0:
            raise ValueError("RewriteArtifact.max_rewrites 必须是正整数")
        if not isinstance(self.rewrites, Mapping):
            raise TypeError("RewriteArtifact.rewrites must be a mapping")
        normalized: dict[str, tuple[str, ...]] = {}
        seen_questions: set[str] = set()
        for question, rewrites in self.rewrites.items():
            if not isinstance(question, str) or not question.strip():
                raise ValueError("RewriteArtifact 问题不能为空")
            normalized_question = " ".join(question.split())
            question_key = normalized_question.casefold()
            if question_key in seen_questions:
                raise ValueError("RewriteArtifact questions must be unique after normalization")
            seen_questions.add(question_key)
            if not isinstance(rewrites, (list, tuple)):
                raise TypeError("RewriteArtifact 改写必须是字符串数组")
            values: list[str] = []
            seen_rewrites: set[str] = set()
            for rewrite in rewrites:
                if not isinstance(rewrite, str) or not rewrite.strip():
                    raise ValueError("RewriteArtifact 改写只能包含非空字符串")
                normalized_rewrite = " ".join(rewrite.split())
                rewrite_key = normalized_rewrite.casefold()
                if rewrite_key == question_key:
                    raise ValueError("RewriteArtifact rewrites cannot repeat the original question")
                if rewrite_key in seen_rewrites:
                    raise ValueError("RewriteArtifact rewrites must be unique")
                seen_rewrites.add(rewrite_key)
                values.append(normalized_rewrite)
            if len(values) > self.max_rewrites:
                raise ValueError("RewriteArtifact 改写数量超过 max_rewrites")
            normalized[normalized_question] = tuple(values)
        object.__setattr__(self, "rewrites", normalized)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RewriteArtifact":
        if not isinstance(payload, Mapping):
            raise TypeError("Rewrite artifact 必须是 JSON 对象")
        expected = {
            "provider",
            "model",
            "max_rewrites",
            "dataset_sha256",
            "rewrites",
        }
        if set(payload) != expected:
            missing = sorted(expected - set(payload))
            unknown = sorted(set(payload) - expected)
            raise ValueError(
                f"Rewrite artifact 字段不匹配: missing={missing}, unknown={unknown}"
            )
        return cls(
            provider=payload["provider"],
            model=payload["model"],
            max_rewrites=payload["max_rewrites"],
            dataset_sha256=payload["dataset_sha256"],
            rewrites=payload["rewrites"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "max_rewrites": self.max_rewrites,
            "dataset_sha256": self.dataset_sha256,
            "rewrites": {
                question: list(rewrites)
                for question, rewrites in self.rewrites.items()
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n"

    def to_rewriter(self, *, max_rewrites: int | None = None) -> MappingQueryRewriter:
        limit = self.max_rewrites if max_rewrites is None else max_rewrites
        return MappingQueryRewriter(self.rewrites, max_rewrites=limit)


def build_rewrite_artifact(
    cases: Sequence[GoldenCase],
    rewriter: QueryRewriter,
    *,
    provider: str,
    model: str,
    max_rewrites: int,
    dataset_sha256: str,
) -> RewriteArtifact:
    if not cases:
        raise ValueError("生成 Rewrite artifact 的评估用例不能为空")
    rewrites: dict[str, tuple[str, ...]] = {}
    seen_questions: set[str] = set()
    for case in cases:
        normalized_question = " ".join(case.question.split())
        if normalized_question.casefold() in seen_questions:
            raise ValueError(f"评估问题重复，无法生成映射: {case.question}")
        seen_questions.add(normalized_question.casefold())
        result = rewriter.rewrite(case.question)
        rewrites[normalized_question] = result.queries[1:]
    return RewriteArtifact(
        provider=provider,
        model=model,
        max_rewrites=max_rewrites,
        dataset_sha256=dataset_sha256,
        rewrites=rewrites,
    )


def load_rewrite_artifact(
    path: str | Path,
    *,
    expected_dataset_sha256: str,
    expected_questions: Sequence[str],
) -> RewriteArtifact:
    artifact_path = Path(path)
    payload = json.loads(
        artifact_path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_json_keys,
    )
    artifact = RewriteArtifact.from_dict(payload)
    if artifact.dataset_sha256 != expected_dataset_sha256:
        raise ValueError("Rewrite artifact 与评估数据集 SHA-256 不匹配")
    expected = {" ".join(question.split()) for question in expected_questions}
    actual = set(artifact.rewrites)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise ValueError(
            f"Rewrite artifact 问题集合不匹配: missing={missing}, unknown={unknown}"
        )
    return artifact
