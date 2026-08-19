"""Deterministic parsing and validation for public ``[文档N]`` citations."""

from __future__ import annotations

import re
from dataclasses import dataclass

CITATION_PARSER_VERSION = "bracketed-document-v1"
_CITATION_PATTERN = re.compile(r"\[文档([1-9]\d*)\]")
_CITATION_LIKE_PATTERN = re.compile(
    r"(?:\[\s*文档\s*\d+\s*\]|文档\s*\d+|来源\s*[:：]\s*[^\s,，。；;]+)"
)


@dataclass(frozen=True, slots=True)
class CitationAnalysis:
    """Low-cardinality citation observations for one generated answer."""

    citations: tuple[int, ...]
    invalid_citations: tuple[str, ...]

    @property
    def has_citations(self) -> bool:
        return bool(self.citations)


def parse_answer_citations(text: str) -> tuple[int, ...]:
    """Return unique exact citation numbers in first-occurrence order."""

    if not isinstance(text, str):
        raise TypeError("引用解析输入必须是字符串")
    citations: list[int] = []
    for match in _CITATION_PATTERN.finditer(text):
        citation = int(match.group(1))
        if citation not in citations:
            citations.append(citation)
    return tuple(citations)


def analyze_answer_citations(text: str, document_count: int) -> CitationAnalysis:
    """Parse exact citations and report malformed or out-of-range markers.

    The parser intentionally does not infer citations from natural-language source
    mentions. Those mentions are retained as diagnostic invalid markers while only
    exact ``[文档N]`` tokens enter the public citation tuple.
    """

    if not isinstance(document_count, int) or isinstance(document_count, bool):
        raise TypeError("document_count 必须是整数")
    if document_count < 0:
        raise ValueError("document_count 不能为负数")
    citations = parse_answer_citations(text)
    invalid: list[str] = []

    for match in _CITATION_PATTERN.finditer(text):
        citation = int(match.group(1))
        if citation > document_count:
            token = match.group(0)
            if token not in invalid:
                invalid.append(token)

    for match in _CITATION_LIKE_PATTERN.finditer(text):
        token = match.group(0)
        if _CITATION_PATTERN.fullmatch(token):
            continue
        if token not in invalid:
            invalid.append(token)

    return CitationAnalysis(tuple(citations), tuple(invalid))
