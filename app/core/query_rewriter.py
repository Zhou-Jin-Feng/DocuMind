"""Query rewriting primitives for retrieval experiments."""

from __future__ import annotations

import json
import re
from hashlib import sha256
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.generator import GenerationConfig


def _normalize_query(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("query rewrite 必须是字符串")
    return " ".join(value.split())


def _required_exact_terms(query: str) -> tuple[str, ...]:
    """Extract command/flag/identifier tokens that rewrites must preserve."""

    normalized = _normalize_query(query)
    terms: list[str] = []
    for command in re.findall(
        r"\b([A-Za-z][A-Za-z0-9_-]*)\s+(?=--[A-Za-z0-9])",
        normalized,
    ):
        if command.casefold() not in {term.casefold() for term in terms}:
            terms.append(command)
    for token in re.findall(
        r"--[A-Za-z0-9][A-Za-z0-9_-]*|"
        r"\b[A-Za-z][A-Za-z0-9]*(?:[_-][A-Za-z0-9]+)+\b",
        normalized,
    ):
        if token.casefold() not in {term.casefold() for term in terms}:
            terms.append(token)
    return tuple(terms)


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError("Query Rewrite JSON cannot contain duplicate keys")
        payload[key] = value
    return payload


@dataclass(frozen=True)
class QueryRewriteResult:
    """Normalized query variants with the original query fixed at rank one."""

    original_query: str
    queries: tuple[str, ...]

    def __post_init__(self) -> None:
        original = _normalize_query(self.original_query)
        if not original:
            raise ValueError("原始查询不能为空")
        normalized = tuple(_normalize_query(query) for query in self.queries)
        if not normalized or normalized[0] != original:
            raise ValueError("queries 第一项必须是规范化后的原始查询")
        if any(not query for query in normalized):
            raise ValueError("query rewrite 不能为空")
        keys = [query.casefold() for query in normalized]
        if len(keys) != len(set(keys)):
            raise ValueError("queries 不能包含重复查询")
        object.__setattr__(self, "original_query", original)
        object.__setattr__(self, "queries", normalized)

    @classmethod
    def from_candidates(
        cls,
        original_query: str,
        candidates: Sequence[str],
        *,
        max_rewrites: int,
    ) -> "QueryRewriteResult":
        if not isinstance(max_rewrites, int) or isinstance(max_rewrites, bool):
            raise TypeError("max_rewrites 必须是整数")
        if max_rewrites < 0:
            raise ValueError("max_rewrites 不能小于 0")
        original = _normalize_query(original_query)
        if not original:
            raise ValueError("原始查询不能为空")

        queries = [original]
        seen = {original.casefold()}
        for candidate in candidates:
            normalized = _normalize_query(candidate)
            key = normalized.casefold()
            if not normalized or key in seen:
                continue
            queries.append(normalized)
            seen.add(key)
            if len(queries) - 1 >= max_rewrites:
                break
        return cls(original_query=original, queries=tuple(queries))


class QueryRewriter(Protocol):
    def rewrite(self, query: str) -> QueryRewriteResult: ...


class IdentityQueryRewriter:
    """No-op implementation useful for composition and smoke tests."""

    def rewrite(self, query: str) -> QueryRewriteResult:
        return QueryRewriteResult.from_candidates(query, (), max_rewrites=0)


class MappingQueryRewriter:
    """Deterministic mapping implementation for tests and reproducible evaluation."""

    def __init__(
        self,
        rewrites_by_query: Mapping[str, Sequence[str]],
        *,
        max_rewrites: int = 2,
    ):
        if not isinstance(max_rewrites, int) or isinstance(max_rewrites, bool):
            raise TypeError("max_rewrites 必须是整数")
        if max_rewrites < 0:
            raise ValueError("max_rewrites 不能小于 0")
        self.max_rewrites = max_rewrites
        self._rewrites = {
            _normalize_query(query).casefold(): tuple(rewrites)
            for query, rewrites in rewrites_by_query.items()
        }

    def rewrite(self, query: str) -> QueryRewriteResult:
        normalized = _normalize_query(query)
        return QueryRewriteResult.from_candidates(
            normalized,
            self._rewrites.get(normalized.casefold(), ()),
            max_rewrites=self.max_rewrites,
        )


class LLMQueryRewriter:
    """Generate query variants through an LLM using a strict JSON contract."""

    SYSTEM_PROMPT = (
        "You rewrite retrieval queries. Return exactly one JSON object with the key "
        '"queries" and a JSON array of strings. Do not return markdown or extra keys. '
        "Each string must be a unique standalone search query that preserves the "
        "user's intent. Preserve command names, flags, identifiers, and quoted terms "
        "verbatim. Do not introduce a product, framework, command, entity, or domain "
        "that is absent from the original question. Never include the original "
        "question in the array."
    )
    USER_PROMPT_TEMPLATE = (
        "Create between 1 and {max_rewrites} unique alternative retrieval queries "
        "for the question below. Do not repeat the original question.\n"
        "{required_terms_instruction}\n"
        "Original question:\n{original_query}"
    )

    def __init__(
        self,
        llm_client: Any,
        *,
        max_rewrites: int = 2,
        max_tokens: int = 256,
    ):
        if not isinstance(max_rewrites, int) or isinstance(max_rewrites, bool):
            raise TypeError("max_rewrites 必须是整数")
        if max_rewrites <= 0:
            raise ValueError("max_rewrites 必须大于 0")
        if not isinstance(max_tokens, int) or isinstance(max_tokens, bool):
            raise TypeError("max_tokens 必须是整数")
        if max_tokens <= 0:
            raise ValueError("max_tokens 必须大于 0")
        if not callable(getattr(llm_client, "generate", None)):
            raise TypeError("llm_client 必须提供 generate 方法")
        self.llm_client = llm_client
        self.max_rewrites = max_rewrites
        self.config = GenerationConfig(
            temperature=0.0,
            max_tokens=max_tokens,
            stream=False,
        )

    @property
    def prompt_sha256(self) -> str:
        canonical_prompt = json.dumps(
            {
                "system": self.SYSTEM_PROMPT,
                "user_template": self.USER_PROMPT_TEMPLATE.format(
                    max_rewrites=self.max_rewrites,
                    required_terms_instruction="{required_terms_instruction}",
                    original_query="{original_query}",
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(canonical_prompt.encode("utf-8")).hexdigest()

    @staticmethod
    def _parse_response(response: str) -> tuple[str, ...]:
        if not isinstance(response, str) or not response.strip():
            raise ValueError("Query Rewrite 模型返回了空响应")
        try:
            payload = json.loads(
                response,
                object_pairs_hook=_reject_duplicate_json_keys,
            )
        except json.JSONDecodeError as exc:
            raise ValueError("Query Rewrite 响应不是合法 JSON") from exc
        if not isinstance(payload, dict) or set(payload) != {"queries"}:
            raise ValueError('Query Rewrite 响应必须只包含 "queries" 字段')
        queries = payload["queries"]
        if not isinstance(queries, list):
            raise ValueError('Query Rewrite 的 "queries" 必须是数组')
        if any(not isinstance(query, str) for query in queries):
            raise ValueError('Query Rewrite 的 "queries" 只能包含字符串')
        if not queries:
            raise ValueError(
                "Query Rewrite response cannot contain an empty queries array"
            )
        normalized: list[str] = []
        seen: set[str] = set()
        for query in queries:
            candidate = _normalize_query(query)
            if not candidate:
                raise ValueError("Query Rewrite response cannot contain an empty query")
            key = candidate.casefold()
            if key in seen:
                raise ValueError(
                    "Query Rewrite response cannot contain duplicate queries"
                )
            seen.add(key)
            normalized.append(candidate)
        return tuple(normalized)

    def rewrite(self, query: str) -> QueryRewriteResult:
        original = _normalize_query(query)
        if not original:
            raise ValueError("原始查询不能为空")
        required_terms = _required_exact_terms(original)
        required_terms_instruction = (
            "Every rewrite must preserve these exact tokens: "
            + ", ".join(required_terms)
            if required_terms
            else "No exact technical tokens are required."
        )
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": self.USER_PROMPT_TEMPLATE.format(
                    max_rewrites=self.max_rewrites,
                    required_terms_instruction=required_terms_instruction,
                    original_query=original,
                ),
            },
        ]
        response = self.llm_client.generate(messages, self.config)
        candidates = self._parse_response(response)
        if len(candidates) > self.max_rewrites:
            raise ValueError("Query Rewrite response exceeded max_rewrites")
        if any(candidate.casefold() == original.casefold() for candidate in candidates):
            raise ValueError("Query Rewrite response cannot repeat the original query")
        for candidate in candidates:
            missing_terms = [
                term
                for term in required_terms
                if term.casefold() not in candidate.casefold()
            ]
            if missing_terms:
                raise ValueError(
                    "Query Rewrite response dropped required exact tokens: "
                    + ", ".join(missing_terms)
                )
        return QueryRewriteResult.from_candidates(
            original,
            candidates,
            max_rewrites=self.max_rewrites,
        )
