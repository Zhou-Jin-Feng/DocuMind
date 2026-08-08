"""Reproducible query-rewrite artifacts for offline retrieval evaluation."""

from __future__ import annotations

import json
from math import isfinite
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.query_rewriter import MappingQueryRewriter, QueryRewriter
from evaluation.models import GoldenCase


ARTIFACT_VERSION = 1


def _validate_sha256(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"RewriteArtifact.{field_name} 必须是字符串")
    normalized = value.strip().casefold()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"RewriteArtifact.{field_name} 必须是 SHA-256 十六进制摘要")
    return normalized


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
    artifact_version: int
    provider: str
    model: str
    max_rewrites: int
    max_tokens: int
    temperature: float
    prompt_sha256: str
    dataset_sha256: str
    rewrites: Mapping[str, tuple[str, ...]]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.artifact_version, int)
            or isinstance(self.artifact_version, bool)
            or self.artifact_version != ARTIFACT_VERSION
        ):
            raise ValueError(
                f"不支持的 Rewrite artifact_version: {self.artifact_version!r}"
            )
        for name in ("provider", "model"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"RewriteArtifact.{name} 不能为空")
            object.__setattr__(self, name, value.strip())
        object.__setattr__(
            self,
            "prompt_sha256",
            _validate_sha256(self.prompt_sha256, "prompt_sha256"),
        )
        object.__setattr__(
            self,
            "dataset_sha256",
            _validate_sha256(self.dataset_sha256, "dataset_sha256"),
        )
        if not isinstance(self.max_rewrites, int) or isinstance(
            self.max_rewrites, bool
        ) or self.max_rewrites <= 0:
            raise ValueError("RewriteArtifact.max_rewrites 必须是正整数")
        if (
            not isinstance(self.max_tokens, int)
            or isinstance(self.max_tokens, bool)
            or self.max_tokens <= 0
        ):
            raise ValueError("RewriteArtifact.max_tokens 必须是正整数")
        if (
            isinstance(self.temperature, bool)
            or not isinstance(self.temperature, (int, float))
            or not isfinite(self.temperature)
            or not 0 <= self.temperature <= 2
        ):
            raise ValueError("RewriteArtifact.temperature 必须是 0 到 2 的有限数字")
        object.__setattr__(self, "temperature", float(self.temperature))
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
            "artifact_version",
            "provider",
            "model",
            "max_rewrites",
            "max_tokens",
            "temperature",
            "prompt_sha256",
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
            artifact_version=payload["artifact_version"],
            provider=payload["provider"],
            model=payload["model"],
            max_rewrites=payload["max_rewrites"],
            max_tokens=payload["max_tokens"],
            temperature=payload["temperature"],
            prompt_sha256=payload["prompt_sha256"],
            dataset_sha256=payload["dataset_sha256"],
            rewrites=payload["rewrites"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_version": self.artifact_version,
            "provider": self.provider,
            "model": self.model,
            "max_rewrites": self.max_rewrites,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "prompt_sha256": self.prompt_sha256,
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
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
            raise ValueError("max_rewrites 必须是非负整数")
        if limit > self.max_rewrites:
            raise ValueError("max_rewrites 不能超过 Rewrite artifact 的生成上限")
        return MappingQueryRewriter(self.rewrites, max_rewrites=limit)


def build_rewrite_artifact(
    cases: Sequence[GoldenCase],
    rewriter: QueryRewriter,
    *,
    provider: str,
    model: str,
    max_rewrites: int,
    max_tokens: int,
    temperature: float,
    prompt_sha256: str,
    dataset_sha256: str,
    existing_rewrites: Mapping[str, Sequence[str]] | None = None,
    progress_callback: Callable[[RewriteArtifact, int, int], None] | None = None,
) -> RewriteArtifact:
    if not cases:
        raise ValueError("生成 Rewrite artifact 的评估用例不能为空")
    normalized_cases: list[tuple[GoldenCase, str]] = []
    seen_questions: set[str] = set()
    for case in cases:
        normalized_question = " ".join(case.question.split())
        if normalized_question.casefold() in seen_questions:
            raise ValueError(f"评估问题重复，无法生成映射: {case.question}")
        seen_questions.add(normalized_question.casefold())
        normalized_cases.append((case, normalized_question))

    artifact_kwargs = {
        "artifact_version": ARTIFACT_VERSION,
        "provider": provider,
        "model": model,
        "max_rewrites": max_rewrites,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "prompt_sha256": prompt_sha256,
        "dataset_sha256": dataset_sha256,
    }
    checkpoint = RewriteArtifact(
        **artifact_kwargs,
        rewrites=existing_rewrites or {},
    )
    expected_questions = {question for _, question in normalized_cases}
    unknown_questions = sorted(set(checkpoint.rewrites) - expected_questions)
    if unknown_questions:
        raise ValueError(
            f"Rewrite checkpoint 包含未知问题: {unknown_questions}"
        )
    rewrites = dict(checkpoint.rewrites)
    total = len(normalized_cases)
    for case, normalized_question in normalized_cases:
        if normalized_question in rewrites:
            continue
        result = rewriter.rewrite(case.question)
        if result.original_query != normalized_question:
            raise ValueError("QueryRewriter 返回的 original_query 与评估问题不一致")
        rewrites[normalized_question] = result.queries[1:]
        checkpoint = RewriteArtifact(**artifact_kwargs, rewrites=rewrites)
        if progress_callback is not None:
            progress_callback(checkpoint, len(rewrites), total)
    return RewriteArtifact(**artifact_kwargs, rewrites=rewrites)


def load_rewrite_artifact_file(path: str | Path) -> RewriteArtifact:
    """Load the strict artifact schema without requiring a complete question set."""

    artifact_path = Path(path)
    payload = json.loads(
        artifact_path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_json_keys,
    )
    return RewriteArtifact.from_dict(payload)


def load_rewrite_artifact(
    path: str | Path,
    *,
    expected_dataset_sha256: str,
    expected_questions: Sequence[str],
) -> RewriteArtifact:
    artifact = load_rewrite_artifact_file(path)
    if artifact.dataset_sha256 != expected_dataset_sha256:
        raise ValueError("Rewrite artifact 与评估数据集 SHA-256 不匹配")
    normalized_expected = [" ".join(question.split()) for question in expected_questions]
    normalized_expected_keys = [question.casefold() for question in normalized_expected]
    if len(normalized_expected_keys) != len(set(normalized_expected_keys)):
        raise ValueError("评估问题规范化后重复，无法加载 Rewrite artifact")
    expected = set(normalized_expected)
    actual = set(artifact.rewrites)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise ValueError(
            f"Rewrite artifact 问题集合不匹配: missing={missing}, unknown={unknown}"
        )
    return artifact
