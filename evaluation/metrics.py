"""Pure retrieval and answer metrics for deterministic unit testing."""

from __future__ import annotations

from collections.abc import Sequence


def _validate_k(k: int) -> None:
    if not isinstance(k, int) or isinstance(k, bool) or k <= 0:
        raise ValueError("k 必须是正整数")


def _expected_set(expected_document_ids: Sequence[str]) -> set[str]:
    return {item.strip() for item in expected_document_ids if item and item.strip()}


def _retrieved_ids(retrieved_document_ids: Sequence[str], k: int) -> list[str]:
    _validate_k(k)
    return [
        item.strip() for item in retrieved_document_ids[:k] if item and item.strip()
    ]


def recall_at_k(
    expected_document_ids: Sequence[str],
    retrieved_document_ids: Sequence[str],
    k: int,
) -> float | None:
    """Return relevant expected documents found in Top-K / expected documents.

    A no-answer case has no positive retrieval target, so recall is ``None`` and
    is excluded from aggregate retrieval metrics.
    """

    expected = _expected_set(expected_document_ids)
    if not expected:
        return None
    retrieved = set(_retrieved_ids(retrieved_document_ids, k))
    return len(expected & retrieved) / len(expected)


def precision_at_k(
    expected_document_ids: Sequence[str],
    retrieved_document_ids: Sequence[str],
    k: int,
) -> float | None:
    """Return relevant retrieved documents / K for answerable cases."""

    expected = _expected_set(expected_document_ids)
    if not expected:
        return None
    retrieved = set(_retrieved_ids(retrieved_document_ids, k))
    return len(expected & retrieved) / k


def reciprocal_rank_at_k(
    expected_document_ids: Sequence[str],
    retrieved_document_ids: Sequence[str],
    k: int,
) -> float | None:
    """Return reciprocal rank of the first relevant document in Top-K."""

    expected = _expected_set(expected_document_ids)
    if not expected:
        return None
    for rank, item in enumerate(_retrieved_ids(retrieved_document_ids, k), 1):
        if item in expected:
            return 1 / rank
    return 0.0


def hit_at_k(
    expected_document_ids: Sequence[str],
    retrieved_document_ids: Sequence[str],
    k: int,
) -> float | None:
    """Return 1 when any expected document enters Top-K, otherwise 0."""

    expected = _expected_set(expected_document_ids)
    if not expected:
        return None
    return float(bool(expected & set(_retrieved_ids(retrieved_document_ids, k))))


def first_relevant_rank(
    expected_document_ids: Sequence[str],
    retrieved_document_ids: Sequence[str],
    k: int,
) -> float | None:
    """Return the 1-based rank of the first relevant document, if present."""

    expected = _expected_set(expected_document_ids)
    if not expected:
        return None
    for rank, item in enumerate(_retrieved_ids(retrieved_document_ids, k), 1):
        if item in expected:
            return float(rank)
    return None


def no_answer_retrieval_accuracy(
    expected_document_ids: Sequence[str],
    retrieved_document_ids: Sequence[str],
    k: int,
) -> float | None:
    """Return 1 when a no-answer case returns no Top-K documents.

    Answerable cases have no applicable value. This metric makes the current
    threshold policy visible instead of silently excluding no-answer cases.
    """

    if _expected_set(expected_document_ids):
        return None
    return float(not _retrieved_ids(retrieved_document_ids, k))


def refusal_accuracy(expected_should_answer: bool, actual_answered: bool) -> float:
    """Return 1 when an answer adapter follows the case's answerability label."""

    if not isinstance(expected_should_answer, bool) or not isinstance(
        actual_answered, bool
    ):
        raise TypeError("拒答评估输入必须是布尔值")
    return float(expected_should_answer == actual_answered)


def keyword_coverage(
    expected_keywords: Sequence[str], answer_text: str
) -> float | None:
    """Return case-insensitive expected-keyword coverage in an answer."""

    keywords = [
        item.strip().casefold() for item in expected_keywords if item and item.strip()
    ]
    if not keywords:
        return None
    normalized_answer = (answer_text or "").casefold()
    return sum(keyword in normalized_answer for keyword in keywords) / len(keywords)


def mean_defined(values: Sequence[float | None]) -> float | None:
    """Average numeric values while excluding not-applicable ``None`` entries."""

    defined = [value for value in values if value is not None]
    return sum(defined) / len(defined) if defined else None
