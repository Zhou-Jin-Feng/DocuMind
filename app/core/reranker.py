"""Cross-Encoder reranking with lazy model loading."""

from __future__ import annotations

import gc
import math
from dataclasses import replace
from typing import Any, Callable, Sequence

import numpy as np

from app.core.retriever import RetrievalResult


class CrossEncoderReranker:
    """Rerank an expanded candidate set while preserving retrieval evidence."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-base",
        *,
        batch_size: int = 16,
        device: str | None = None,
        local_files_only: bool = False,
        model_factory: Callable[..., Any] | None = None,
    ):
        normalized_model = (model_name or "").strip()
        if not normalized_model:
            raise ValueError("model_name 不能为空")
        if (
            not isinstance(batch_size, int)
            or isinstance(batch_size, bool)
            or batch_size <= 0
        ):
            raise ValueError("batch_size 必须是大于 0 的整数")
        self.model_name = normalized_model
        self.batch_size = batch_size
        self.device = (device or "").strip() or None
        if not isinstance(local_files_only, bool):
            raise TypeError("local_files_only 必须是布尔值")
        self.local_files_only = local_files_only
        self._model_factory = model_factory
        self._model: Any | None = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def _load_model(self) -> Any:
        if self._model is None:
            factory = self._model_factory
            if factory is None:
                try:
                    from sentence_transformers import CrossEncoder
                except ImportError as exc:
                    raise RuntimeError(
                        "Cross-Encoder 重排需要安装 sentence-transformers"
                    ) from exc
                factory = CrossEncoder
            kwargs = {"device": self.device} if self.device else {}
            if self.local_files_only:
                kwargs["local_files_only"] = True
            self._model = factory(self.model_name, **kwargs)
        return self._model

    def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievalResult],
        *,
        top_k: int,
    ) -> list[RetrievalResult]:
        normalized_query = " ".join((query or "").split())
        if not normalized_query:
            raise ValueError("query 不能为空")
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k <= 0:
            raise ValueError("top_k 必须是大于 0 的整数")
        if not candidates:
            return []

        model = self._load_model()
        pairs = [(normalized_query, candidate.content) for candidate in candidates]
        raw_scores = model.predict(
            pairs,
            batch_size=self.batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        scores = np.asarray(raw_scores, dtype=float).reshape(-1)
        if len(scores) != len(candidates):
            raise ValueError(
                f"Cross-Encoder 分数数量({len(scores)})与候选数量({len(candidates)})不匹配"
            )
        if any(not math.isfinite(float(score)) for score in scores):
            raise ValueError("Cross-Encoder 返回了非有限分数")

        scored = [
            (
                replace(
                    candidate,
                    metadata=dict(candidate.metadata),
                    rerank_score=float(score),
                ),
                index,
            )
            for index, (candidate, score) in enumerate(zip(candidates, scores))
        ]
        scored.sort(key=lambda item: (-float(item[0].rerank_score), item[1]))
        results = [item[0] for item in scored[:top_k]]
        for rank, result in enumerate(results, 1):
            result.rank = rank
        return results

    def close(self) -> None:
        self._model = None
        gc.collect()
