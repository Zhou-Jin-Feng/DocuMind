"""
RAG 检索策略及统一结果模型。

语义检索使用 L2 距离，值越小越相关；BM25、RRF 和重排分数均是值越大
越相关。调用方不能把这些分数直接放在同一阈值尺度上比较。
"""

import hashlib
import math
import re
from dataclasses import dataclass, field, replace
from time import perf_counter
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

from rich.panel import Panel

from app.observability.metrics import get_metrics
from app.observability.tracing import trace_span
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RetrievalResult:
    """
    不同检索策略共享的结果模型。

    ``distance`` 是越小越好的 L2 距离；其余 score 字段越大越好。各阶段
    保留自己的排名和分数，便于解释混合检索结果，而不覆盖原始信号。
    """

    content: str
    metadata: Dict
    distance: Optional[float]
    rank: int
    source: str = ""
    page_number: Optional[int] = None
    rerank_score: Optional[float] = None
    lexical_score: Optional[float] = None
    dense_rank: Optional[int] = None
    lexical_rank: Optional[int] = None
    fusion_score: Optional[float] = None
    query_fusion_score: Optional[float] = None
    query_ranks: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """把来源和用户可读页码从统一元数据中提升为常用字段。"""
        self.metadata = self.metadata or {}
        self.source = str(
            self.metadata.get("source_file")
            or self.metadata.get("source")
            or self.source
        )
        page = self.metadata.get("page_number")
        if isinstance(page, int) and page > 0:
            self.page_number = page

    @property
    def page(self) -> int:
        """兼容旧调用；无页码时返回 0。"""
        return self.page_number or 0


class Retriever:
    """封装查询向量化、Milvus 语义检索和轻量重排。"""

    def __init__(self, vector_store, embedding_client):
        self.vector_store = vector_store
        self.embedding_client = embedding_client
        logger.info("检索器初始化完成")

    def retrieve_semantic(
        self,
        query: str,
        top_k: int = 5,
        score_threshold: Optional[float] = None,
        metadata_filter: Optional[Dict] = None,
        result_predicate: Optional[Callable[[Dict], bool]] = None,
    ) -> List[RetrievalResult]:
        """
        执行语义检索，``score_threshold`` 表示允许的最大 L2 距离。

        ``metadata_filter`` 会下推给 Milvus；``result_predicate`` 只能在返回后
        执行，因此启用谓词时会多取候选，再截断为 ``top_k``。Embedding 或
        向量检索失败会在记录指标和日志后原样抛出，不静默降级为空结果。
        """
        normalized_query = (query or "").strip()
        if not normalized_query:
            raise ValueError("查询内容不能为空")
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")
        if score_threshold is not None and (
            not math.isfinite(float(score_threshold)) or float(score_threshold) < 0
        ):
            raise ValueError("score_threshold 必须是非负有限数")

        metrics = get_metrics()
        provider = str(getattr(self.embedding_client, "provider", "unknown"))
        with trace_span(
            "rag.retrieve",
            attributes={
                "provider": provider,
                "query.length": len(normalized_query),
                "retrieval.top_k": top_k,
            },
        ):
            retrieval_started = perf_counter()
            logger.info(
                "开始语义检索",
                event="retrieval_started",
                operation="rag.retrieve",
                status="started",
                query_length=len(normalized_query),
                top_k=top_k,
                distance_threshold=score_threshold,
                provider=provider,
            )

            embedding_started = perf_counter()
            try:
                with trace_span(
                    "embedding.query",
                    attributes={"provider": provider},
                ):
                    query_embedding = self.embedding_client.embed_text(normalized_query)
            except Exception as exc:
                embedding_duration = perf_counter() - embedding_started
                retrieval_duration = perf_counter() - retrieval_started
                metrics.observe_embedding(
                    provider, "embedding.query", "error", embedding_duration
                )
                metrics.observe_retrieval(provider, "error", retrieval_duration)
                metrics.record_component_error("embedding.query", type(exc).__name__)
                logger.exception(
                    "查询向量化失败",
                    event="query_embedding_failed",
                    operation="embedding.query",
                    duration_ms=embedding_duration * 1000,
                    status="error",
                    error_type=type(exc).__name__,
                    provider=provider,
                )
                logger.error(
                    "语义检索失败",
                    event="retrieval_failed",
                    operation="rag.retrieve",
                    duration_ms=retrieval_duration * 1000,
                    status="error",
                    error_type=type(exc).__name__,
                    provider=provider,
                )
                raise

            embedding_duration = perf_counter() - embedding_started
            metrics.observe_embedding(
                provider, "embedding.query", "success", embedding_duration
            )
            logger.info(
                "查询向量化完成",
                event="query_embedding_completed",
                operation="embedding.query",
                duration_ms=embedding_duration * 1000,
                status="success",
                provider=provider,
                embedding_dimension=len(query_embedding),
            )

            search_started = perf_counter()
            try:
                with trace_span(
                    "vector.search",
                    attributes={
                        "provider": provider,
                        "retrieval.top_k": top_k,
                    },
                ):
                    ensure_embedding_space = getattr(
                        self.vector_store,
                        "ensure_embedding_space",
                        None,
                    )
                    if callable(ensure_embedding_space):
                        embedding_config = (
                            getattr(self.embedding_client, "config", {}) or {}
                        )
                        embedding_model = str(
                            embedding_config.get("model")
                            or getattr(
                                self.embedding_client,
                                "model_name",
                                "unknown",
                            )
                        )
                        ensure_embedding_space(
                            provider,
                            embedding_model,
                            len(query_embedding),
                        )
                    # 内存谓词无法下推，过取候选以降低过滤后不足 top_k 的概率。
                    search_results = self.vector_store.search(
                        query_embedding=query_embedding,
                        n_results=(
                            max(top_k * 5, top_k) if result_predicate else top_k
                        ),
                        where=metadata_filter,
                    )
            except Exception as exc:
                search_duration = perf_counter() - search_started
                retrieval_duration = perf_counter() - retrieval_started
                metrics.observe_retrieval(provider, "error", retrieval_duration)
                metrics.record_component_error("vector.search", type(exc).__name__)
                logger.exception(
                    "向量检索失败",
                    event="vector_search_failed",
                    operation="vector.search",
                    duration_ms=search_duration * 1000,
                    status="error",
                    error_type=type(exc).__name__,
                )
                logger.error(
                    "语义检索失败",
                    event="retrieval_failed",
                    operation="rag.retrieve",
                    duration_ms=retrieval_duration * 1000,
                    status="error",
                    error_type=type(exc).__name__,
                    provider=provider,
                )
                raise

            results: List[RetrievalResult] = []
            for document, metadata, distance in zip(
                search_results["documents"],
                search_results["metadatas"],
                search_results["distances"],
            ):
                numeric_distance = float(distance)
                if score_threshold is not None and numeric_distance > score_threshold:
                    continue
                if result_predicate is not None and not result_predicate(
                    metadata or {}
                ):
                    continue
                results.append(
                    RetrievalResult(
                        content=document,
                        metadata=metadata or {},
                        distance=numeric_distance,
                        rank=len(results) + 1,
                    )
                )
                if len(results) >= top_k:
                    break

            retrieval_duration = perf_counter() - retrieval_started
            metrics.observe_retrieval(
                provider,
                "success",
                retrieval_duration,
                result_count=len(results),
            )
            logger.info(
                "语义检索完成",
                event="retrieval_completed",
                operation="rag.retrieve",
                duration_ms=retrieval_duration * 1000,
                status="success",
                provider=provider,
                result_count=len(results),
                raw_result_count=len(search_results["documents"]),
            )
            return results

    def retrieve_with_context(
        self,
        query: str,
        top_k: int = 5,
        expand_context: bool = False,
    ) -> List[RetrievalResult]:
        """执行标准检索；相邻 Chunk 扩展留待文档生命周期版本实现。"""
        results = self.retrieve_semantic(query, top_k)
        if expand_context:
            logger.warning("上下文扩展尚未启用，当前返回标准检索结果")
        return results

    @staticmethod
    def _keyword_terms(text: str) -> set[str]:
        """提取英文词、中文单字和中文二元组，避免依赖空格分词。"""
        normalized = (text or "").lower()
        terms = set(re.findall(r"[a-z0-9_]+", normalized))
        for sequence in re.findall(r"[\u4e00-\u9fff]+", normalized):
            terms.update(sequence)
            terms.update(
                sequence[index : index + 2] for index in range(len(sequence) - 1)
            )
        return terms

    @staticmethod
    def rerank_results(
        results: List[RetrievalResult],
        query: str,
        top_k: int = 3,
    ) -> List[RetrievalResult]:
        """按 70% 距离相似度和 30% 关键词覆盖率进行轻量重排。"""
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")
        if not results:
            return []

        query_terms = Retriever._keyword_terms(query)
        for result in results:
            content_terms = Retriever._keyword_terms(result.content)
            keyword_overlap = (
                len(query_terms & content_terms) / len(query_terms)
                if query_terms
                else 0.0
            )
            distance_similarity = (
                1 / (1 + max(result.distance, 0.0))
                if result.distance is not None
                else 0.0
            )
            result.rerank_score = 0.7 * distance_similarity + 0.3 * keyword_overlap

        reranked = sorted(
            results,
            key=lambda result: (
                result.rerank_score if result.rerank_score is not None else -1.0
            ),
            reverse=True,
        )[:top_k]
        for rank, result in enumerate(reranked, 1):
            result.rank = rank

        logger.info(f"重排序完成: input={len(results)}, output={len(reranked)}")
        return reranked

    @staticmethod
    def format_results_for_llm(results: List[RetrievalResult]) -> str:
        """将结果格式化成包含来源和页码的 LLM 上下文。"""
        if not results:
            return "未找到相关信息。"

        context_parts = []
        for index, result in enumerate(results, 1):
            page = f"，第 {result.page_number} 页" if result.page_number else ""
            context_parts.append(
                f"[文档{index}] 来源: {result.source or '未知'}{page}\n{result.content}\n"
            )
        return "\n".join(context_parts)

    @staticmethod
    def display_results(
        results: List[RetrievalResult], title: str = "检索结果"
    ) -> None:
        """以普通日志输出检索结果摘要。"""
        logger.info(f"{title}: {len(results)} 条")
        for result in results:
            rerank = (
                f", rerank={result.rerank_score:.4f}"
                if result.rerank_score is not None
                else ""
            )
            distance = (
                f"{result.distance:.4f}" if result.distance is not None else "N/A"
            )
            logger.info(
                f"排名 {result.rank}: distance={distance}{rerank}, "
                f"source={result.source or '未知'}"
            )


class BM25Retriever:
    """在固定 Chunk 集合上提供可复现的 BM25 词法检索。"""

    def __init__(self, documents: Iterable[Any]):
        self._documents = tuple(
            self._normalize_document(document) for document in documents
        )
        if not self._documents:
            raise ValueError("BM25 文档集合不能为空")
        from rank_bm25 import BM25Okapi

        self._bm25_class = BM25Okapi
        self._tokenized_documents = tuple(
            self.tokenize(content) for content, _ in self._documents
        )
        self._bm25 = BM25Okapi(self._tokenized_documents)

    @staticmethod
    def tokenize(text: str) -> list[str]:
        """
        同时生成 Jieba 词、中文单字和二元组。

        冗余粒度是有意设计：词语负责语义完整性，单字和二元组减少专有名词
        未登录或分词边界错误造成的漏召回。
        """
        normalized = (text or "").casefold()
        terms = re.findall(r"[a-z0-9_]+", normalized)
        import jieba

        for sequence in re.findall(r"[\u4e00-\u9fff]+", normalized):
            terms.extend(
                token for token in jieba.lcut(sequence, cut_all=False) if token.strip()
            )
            terms.extend(sequence)
            terms.extend(
                sequence[index : index + 2] for index in range(len(sequence) - 1)
            )
        return terms

    @staticmethod
    def _normalize_document(document: Any) -> tuple[str, dict[str, Any]]:
        content = str(
            getattr(document, "page_content", getattr(document, "content", "")) or ""
        )
        metadata = dict(getattr(document, "metadata", {}) or {})
        if not content.strip():
            raise ValueError("BM25 文档内容不能为空")
        return content, metadata

    @staticmethod
    def _document_key(content: str, metadata: Mapping[str, Any]) -> str:
        """优先用稳定 Chunk ID；旧数据则根据文档身份和正文生成去重键。"""
        chunk_id = metadata.get("chunk_id")
        if chunk_id:
            return str(chunk_id)
        document_id = str(metadata.get("document_id") or "")
        payload = f"{document_id}\0{content}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _matches_filter(
        metadata: Mapping[str, Any],
        metadata_filter: Mapping[str, Any] | None,
    ) -> bool:
        return not metadata_filter or all(
            metadata.get(key) == value for key, value in metadata_filter.items()
        )

    def retrieve_lexical(
        self,
        query: str,
        top_k: int = 5,
        metadata_filter: Optional[Dict] = None,
        result_predicate: Optional[Callable[[Dict], bool]] = None,
        lexical_score_threshold: Optional[float] = None,
    ) -> List[RetrievalResult]:
        """
        返回 BM25 Top-K，``lexical_score_threshold`` 是允许的最小分数。

        过滤子集时重新建立 BM25 模型，使 IDF 基于实际候选集合计算；额外
        要求查询与候选至少共享一个 Token，避免全零分结果进入上下文。
        """
        normalized_query = (query or "").strip()
        if not normalized_query:
            raise ValueError("查询内容不能为空")
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")
        if lexical_score_threshold is not None and (
            not math.isfinite(float(lexical_score_threshold))
            or float(lexical_score_threshold) < 0
        ):
            raise ValueError("lexical_score_threshold 必须是非负有限数")
        query_tokens = self.tokenize(normalized_query)
        if not query_tokens:
            return []
        eligible_indexes = [
            index
            for index, (_, metadata) in enumerate(self._documents)
            if self._matches_filter(metadata, metadata_filter)
            and (result_predicate is None or result_predicate(metadata))
        ]
        if not eligible_indexes:
            return []
        if len(eligible_indexes) == len(self._documents):
            scores = self._bm25.get_scores(query_tokens)
        else:
            filtered_model = self._bm25_class(
                [self._tokenized_documents[index] for index in eligible_indexes]
            )
            scores = filtered_model.get_scores(query_tokens)
        query_term_set = set(query_tokens)
        ranked = [
            (document_index, float(score))
            for document_index, score in zip(eligible_indexes, scores)
            if query_term_set.intersection(self._tokenized_documents[document_index])
            and (
                lexical_score_threshold is None
                or float(score) >= float(lexical_score_threshold)
            )
        ]
        ranked.sort(key=lambda item: (-item[1], item[0]))
        return [
            RetrievalResult(
                content=self._documents[index][0],
                metadata=self._documents[index][1],
                distance=None,
                rank=rank,
                lexical_score=score,
                lexical_rank=rank,
            )
            for rank, (index, score) in enumerate(ranked[:top_k], 1)
        ]


class HybridRetriever:
    """
    使用加权倒数排名融合（RRF）合并语义检索与 BM25。

    RRF 只依赖名次，不直接比较 L2 距离和 BM25 分数，因此适合融合量纲
    不同的检索信号；相同 Chunk 通过稳定键去重并累加两路贡献。
    """

    def __init__(
        self,
        dense_retriever: Retriever,
        lexical_retriever: BM25Retriever,
        *,
        rrf_k: int = 60,
        dense_weight: float = 1.0,
        lexical_weight: float = 1.0,
        candidate_multiplier: int = 5,
    ):
        if not isinstance(rrf_k, int) or isinstance(rrf_k, bool) or rrf_k <= 0:
            raise ValueError("rrf_k 必须大于 0")
        if (
            not isinstance(candidate_multiplier, int)
            or isinstance(candidate_multiplier, bool)
            or candidate_multiplier <= 0
        ):
            raise ValueError("candidate_multiplier 必须是大于 0 的整数")
        for name, weight in (
            ("dense_weight", dense_weight),
            ("lexical_weight", lexical_weight),
        ):
            if not math.isfinite(float(weight)) or float(weight) < 0:
                raise ValueError(f"{name} 必须是非负有限数")
        if float(dense_weight) == 0 and float(lexical_weight) == 0:
            raise ValueError("dense_weight 和 lexical_weight 不能同时为 0")
        self.dense_retriever = dense_retriever
        self.lexical_retriever = lexical_retriever
        self.rrf_k = rrf_k
        self.dense_weight = float(dense_weight)
        self.lexical_weight = float(lexical_weight)
        self.candidate_multiplier = candidate_multiplier

    @staticmethod
    def _document_key(result: RetrievalResult) -> str:
        return BM25Retriever._document_key(result.content, result.metadata)

    def retrieve_hybrid(
        self,
        query: str,
        top_k: int = 5,
        *,
        dense_top_k: Optional[int] = None,
        lexical_top_k: Optional[int] = None,
        candidate_multiplier: Optional[int] = None,
        score_threshold: Optional[float] = None,
        lexical_score_threshold: Optional[float] = None,
        metadata_filter: Optional[Dict] = None,
        result_predicate: Optional[Callable[[Dict], bool]] = None,
    ) -> List[RetrievalResult]:
        """分别扩大两路候选集，按权重计算 RRF 后返回最终 Top-K。"""
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")
        multiplier = (
            self.candidate_multiplier
            if candidate_multiplier is None
            else candidate_multiplier
        )
        if (
            not isinstance(multiplier, int)
            or isinstance(multiplier, bool)
            or multiplier <= 0
        ):
            raise ValueError("candidate_multiplier 必须是大于 0 的整数")
        if dense_top_k is not None and dense_top_k <= 0:
            raise ValueError("dense_top_k 必须大于 0")
        if lexical_top_k is not None and lexical_top_k <= 0:
            raise ValueError("lexical_top_k 必须大于 0")
        candidate_k = max(top_k * multiplier, top_k)
        dense_results = (
            self.dense_retriever.retrieve_semantic(
                query,
                top_k=dense_top_k or candidate_k,
                score_threshold=score_threshold,
                metadata_filter=metadata_filter,
                result_predicate=result_predicate,
            )
            if self.dense_weight > 0
            else []
        )
        lexical_kwargs: dict[str, Any] = {
            "top_k": lexical_top_k or candidate_k,
            "metadata_filter": metadata_filter,
            "result_predicate": result_predicate,
        }
        if lexical_score_threshold is not None:
            lexical_kwargs["lexical_score_threshold"] = lexical_score_threshold
        lexical_results = (
            self.lexical_retriever.retrieve_lexical(query, **lexical_kwargs)
            if self.lexical_weight > 0
            else []
        )
        merged: dict[str, RetrievalResult] = {}
        if self.dense_weight > 0:
            for rank, result in enumerate(dense_results, 1):
                result.dense_rank = rank
                result.fusion_score = self.dense_weight / (self.rrf_k + rank)
                merged[self._document_key(result)] = result
        if self.lexical_weight > 0:
            for rank, result in enumerate(lexical_results, 1):
                key = self._document_key(result)
                contribution = self.lexical_weight / (self.rrf_k + rank)
                existing = merged.get(key)
                if existing is None:
                    result.lexical_rank = rank
                    result.fusion_score = contribution
                    merged[key] = result
                else:
                    existing.lexical_rank = rank
                    existing.lexical_score = result.lexical_score
                    existing.fusion_score = (
                        existing.fusion_score or 0.0
                    ) + contribution
        results = sorted(
            merged.values(),
            key=lambda result: (
                -(result.fusion_score or 0.0),
                result.dense_rank or 10**9,
                result.lexical_rank or 10**9,
            ),
        )[:top_k]
        for rank, result in enumerate(results, 1):
            result.rank = rank
        return results

    def retrieve_semantic(
        self,
        query: str,
        top_k: int = 5,
        **kwargs: Any,
    ) -> List[RetrievalResult]:
        """兼容统一 Retriever 契约，实际执行混合检索。"""
        return self.retrieve_hybrid(query, top_k=top_k, **kwargs)


class MultiQueryRetriever:
    """
    独立执行原查询及其改写，并用 RRF 融合结果。

    原查询必须保留在首位，保证改写质量不佳时仍有基础召回；融合强制依赖
    ``metadata.chunk_id``，否则无法可靠判断不同查询命中的是否为同一 Chunk。
    """

    SUPPORTED_METHODS = {
        "retrieve_semantic",
        "retrieve_lexical",
        "retrieve_hybrid",
    }

    def __init__(
        self,
        base_retriever: Any,
        query_rewriter: Any,
        *,
        retrieval_method: str = "retrieve_semantic",
        rrf_k: int = 60,
        candidate_multiplier: int = 1,
    ):
        if retrieval_method not in self.SUPPORTED_METHODS or not callable(
            getattr(base_retriever, retrieval_method, None)
        ):
            raise ValueError(f"retrieval_method 不可调用: {retrieval_method}")
        if not callable(getattr(query_rewriter, "rewrite", None)):
            raise TypeError("query_rewriter 必须提供 rewrite 方法")
        if not isinstance(rrf_k, int) or isinstance(rrf_k, bool) or rrf_k <= 0:
            raise ValueError("rrf_k 必须是大于 0 的整数")
        if (
            not isinstance(candidate_multiplier, int)
            or isinstance(candidate_multiplier, bool)
            or candidate_multiplier <= 0
        ):
            raise ValueError("candidate_multiplier 必须是大于 0 的整数")
        self.base_retriever = base_retriever
        self.query_rewriter = query_rewriter
        self.retrieval_method = retrieval_method
        self.rrf_k = rrf_k
        self.candidate_multiplier = candidate_multiplier
        self.last_queries: tuple[str, ...] = ()

    @staticmethod
    def _chunk_id(result: RetrievalResult) -> str:
        """取得跨查询去重所需的稳定 Chunk 身份。"""
        chunk_id = (result.metadata or {}).get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            raise ValueError("多查询融合要求每条候选都包含稳定 metadata.chunk_id")
        return chunk_id.strip()

    def _retrieve(
        self,
        query: str,
        top_k: int,
        **kwargs: Any,
    ) -> List[RetrievalResult]:
        """执行多查询召回，并保留每个改写查询贡献的排名用于解释。"""
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k <= 0:
            raise ValueError("top_k 必须是大于 0 的整数")
        rewrite_result = self.query_rewriter.rewrite(query)
        queries = tuple(getattr(rewrite_result, "queries", ()))
        if not queries:
            raise ValueError("query_rewriter 未返回任何查询")
        original = " ".join((query or "").split())
        if queries[0] != original:
            raise ValueError("query_rewriter 必须将原始查询保留在第一项")
        self.last_queries = queries

        candidate_k = max(top_k * self.candidate_multiplier, top_k)
        method = getattr(self.base_retriever, self.retrieval_method)
        merged: dict[str, RetrievalResult] = {}
        first_seen: dict[str, int] = {}
        sequence = 0
        for rewritten_query in queries:
            results = method(rewritten_query, top_k=candidate_k, **kwargs)
            seen_in_query: set[str] = set()
            for rank, result in enumerate(results, 1):
                chunk_id = self._chunk_id(result)
                if chunk_id in seen_in_query:
                    continue
                seen_in_query.add(chunk_id)
                contribution = 1.0 / (self.rrf_k + rank)
                existing = merged.get(chunk_id)
                if existing is None:
                    merged[chunk_id] = replace(
                        result,
                        metadata=dict(result.metadata),
                        query_fusion_score=contribution,
                        query_ranks={rewritten_query: rank},
                    )
                    first_seen[chunk_id] = sequence
                    sequence += 1
                else:
                    merged[chunk_id] = replace(
                        existing,
                        query_fusion_score=(existing.query_fusion_score or 0.0)
                        + contribution,
                        query_ranks={**existing.query_ranks, rewritten_query: rank},
                    )

        results = sorted(
            merged.values(),
            key=lambda result: (
                -(result.query_fusion_score or 0.0),
                min(result.query_ranks.values(), default=10**9),
                first_seen[self._chunk_id(result)],
            ),
        )[:top_k]
        for rank, result in enumerate(results, 1):
            result.rank = rank
        return results

    def retrieve_semantic(
        self,
        query: str,
        top_k: int = 5,
        **kwargs: Any,
    ) -> List[RetrievalResult]:
        return self._retrieve(query, top_k, **kwargs)

    def retrieve_lexical(
        self,
        query: str,
        top_k: int = 5,
        **kwargs: Any,
    ) -> List[RetrievalResult]:
        return self._retrieve(query, top_k, **kwargs)

    def retrieve_hybrid(
        self,
        query: str,
        top_k: int = 5,
        **kwargs: Any,
    ) -> List[RetrievalResult]:
        return self._retrieve(query, top_k, **kwargs)


class RerankingRetriever:
    """
    扩大基础检索候选集，再交给独立精排器选择最终 Top-K。

    ``candidate_multiplier`` 控制召回率与 Cross-Encoder 推理成本之间的取舍。
    """

    def __init__(
        self,
        base_retriever: Any,
        reranker: Any,
        *,
        retrieval_method: str = "retrieve_semantic",
        candidate_multiplier: int = 5,
    ):
        if (
            retrieval_method not in MultiQueryRetriever.SUPPORTED_METHODS
            or not callable(getattr(base_retriever, retrieval_method, None))
        ):
            raise ValueError(f"retrieval_method 不可调用: {retrieval_method}")
        if not callable(getattr(reranker, "rerank", None)):
            raise TypeError("reranker 必须提供 rerank 方法")
        if (
            not isinstance(candidate_multiplier, int)
            or isinstance(candidate_multiplier, bool)
            or candidate_multiplier <= 0
        ):
            raise ValueError("candidate_multiplier 必须是大于 0 的整数")
        self.base_retriever = base_retriever
        self.reranker = reranker
        self.retrieval_method = retrieval_method
        self.candidate_multiplier = candidate_multiplier

    def _retrieve(
        self,
        query: str,
        top_k: int,
        **kwargs: Any,
    ) -> List[RetrievalResult]:
        """按倍数召回候选，最终数量仍由调用方的 ``top_k`` 决定。"""
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k <= 0:
            raise ValueError("top_k 必须是大于 0 的整数")
        candidate_k = max(top_k * self.candidate_multiplier, top_k)
        method = getattr(self.base_retriever, self.retrieval_method)
        candidates = method(query, top_k=candidate_k, **kwargs)
        return self.reranker.rerank(query, candidates, top_k=top_k)

    def retrieve_semantic(
        self,
        query: str,
        top_k: int = 5,
        **kwargs: Any,
    ) -> List[RetrievalResult]:
        return self._retrieve(query, top_k, **kwargs)

    def retrieve_lexical(
        self,
        query: str,
        top_k: int = 5,
        **kwargs: Any,
    ) -> List[RetrievalResult]:
        return self._retrieve(query, top_k, **kwargs)

    def retrieve_hybrid(
        self,
        query: str,
        top_k: int = 5,
        **kwargs: Any,
    ) -> List[RetrievalResult]:
        return self._retrieve(query, top_k, **kwargs)


def demo_retrieval():
    """
    演示：完整的检索流程
    """
    logger.info("=" * 60)

    # 导入依赖模块
    try:
        from app.core.vector_store import VectorStore
        from app.core.embedding_client import UniversalEmbeddingClient
        from app.core.document_loader import UniversalDocumentLoader
        from app.core.document_chunker import DocumentChunker
    except ImportError as e:
        logger.info(f"导入失败: {str(e)}")
        logger.info("请确保前面课程的脚本都在同一目录")
        return

    import os

    # 步骤1：准备知识库
    logger.info("\n步骤1: 准备知识库文档")

    knowledge_content = """
机器学习算法详解

第一章：监督学习
监督学习是最常见的机器学习方法。它使用标记的训练数据来训练模型。主要算法包括：

1. 线性回归：用于预测连续值，如房价预测、销量预测等。
2. 逻辑回归：用于二分类问题，如垃圾邮件识别、用户流失预测。
3. 决策树：通过树状结构进行决策，可用于分类和回归。
4. 随机森林：集成多个决策树，提高预测准确性和稳定性。
5. 支持向量机(SVM)：寻找最优超平面进行分类，适合高维数据。
6. 神经网络：模拟人脑神经元结构，可处理复杂的非线性问题。

第二章：无监督学习
无监督学习处理未标记的数据，主要用于发现数据中的隐藏模式。

1. K-means聚类：将数据分为K个簇，常用于用户分群、图像分割。
2. 层次聚类：构建树状聚类结构，适合探索性数据分析。
3. 主成分分析(PCA)：降维技术，减少特征数量同时保留主要信息。
4. 自编码器：使用神经网络进行降维和特征学习。

第三章：深度学习
深度学习是机器学习的一个分支，使用多层神经网络。

1. 卷积神经网络(CNN)：专门用于处理图像数据，在计算机视觉领域表现出色。
2. 循环神经网络(RNN)：处理序列数据，如文本、时间序列。
3. 长短期记忆网络(LSTM)：RNN的改进版，解决了长期依赖问题。
4. Transformer：基于注意力机制，在自然语言处理领域取得突破性进展。
5. 生成对抗网络(GAN)：由生成器和判别器组成，可生成逼真的图像和内容。

第四章：强化学习
强化学习通过与环境交互来学习最优策略。

1. Q-learning：基于值函数的方法，学习状态-动作的价值。
2. Deep Q-Network(DQN)：结合深度学习和Q-learning。
3. 策略梯度：直接学习策略函数。
4. Actor-Critic：结合值函数和策略函数的优势。

第五章：RAG系统架构
检索增强生成(RAG)是一种新兴的AI系统架构。它包含以下核心组件：

1. 文档加载器：解析PDF、Word、TXT等格式的文档。
2. 文本分块器：将长文档切分为适合检索的片段。
3. 向量化模型：将文本转换为高维向量表示。
4. 向量数据库：存储和快速检索文档向量。
5. 检索器：根据用户问题找到最相关的文档片段。
6. 生成器：基于检索到的上下文生成答案。

RAG的优势在于结合了知识检索和生成能力，可以提供有据可查的准确答案。
    """.strip()

    kb_file = "knowledge_base.txt"
    with open(kb_file, "w", encoding="utf-8") as f:
        f.write(knowledge_content)

    logger.info(f"已创建知识库: {kb_file}")
    logger.info(f"  字符数: {len(knowledge_content):,}")

    # 步骤2：加载和分块
    logger.info("\n步骤2: 加载并分块文档")

    loader = UniversalDocumentLoader()
    documents = loader.load_document(kb_file)

    chunker = DocumentChunker(chunk_size=300, chunk_overlap=50)
    chunks = chunker.chunk_documents_recursive(documents)

    logger.info(f"分块结果: {len(chunks)} 个块")

    # 步骤3：向量化并存储
    logger.info("\n步骤3: 向量化并存储到向量库")

    try:
        provider = os.getenv("DEFAULT_EMBEDDING_PROVIDER", "openai")
        embedding_client = UniversalEmbeddingClient(provider)

        texts = [chunk.page_content for chunk in chunks]
        embeddings = embedding_client.embed_texts_batch(texts, show_progress=True)

    except Exception as e:
        logger.info(f"使用真实向量失败: {str(e)}")
        logger.info("使用模拟向量继续演示...")

        import random

        embeddings = [[random.random() for _ in range(1536)] for _ in chunks]
        embedding_client = None  # 标记为模拟模式

    # 创建向量库
    vector_store = VectorStore(
        collection_name="retrieval_demo",
        uri=settings.milvus_uri,
        token=settings.milvus_token,
        db_name=settings.milvus_db_name,
    )
    embedding_config = getattr(embedding_client, "config", {}) or {}
    vector_store.ensure_embedding_space(
        getattr(embedding_client, "provider", "demo"),
        str(embedding_config.get("model") or "simulated"),
        len(embeddings[0]),
    )
    vector_store.add_documents(chunks, embeddings)

    # 步骤4：初始化检索器
    logger.info("\n步骤4: 初始化检索器")

    if embedding_client is None:
        logger.info("模拟模式，无法测试真实检索")
        vector_store.close()
        return

    retriever = Retriever(vector_store, embedding_client)

    # 步骤5：测试不同的查询
    logger.info("\n" + "=" * 70)
    logger.info("\n步骤5: 测试检索功能")

    test_queries = [
        "监督学习有哪些常见算法？",
        "深度学习和机器学习的区别",
        "RAG系统包含哪些组件？",
    ]

    for i, query in enumerate(test_queries, 1):
        logger.info("\n" + "=" * 70)
        logger.info(f"\n查询 {i}: {query}")

        # 执行检索
        results = retriever.retrieve_semantic(query, top_k=3)

        # 显示结果
        Retriever.display_results(results, title=f"语义检索结果 - 查询{i}")

        # 格式化为LLM上下文
        if i == 1:  # 只在第一个查询展示上下文格式
            logger.info("\n格式化为LLM上下文:")
            llm_context = Retriever.format_results_for_llm(results[:2])
            logger.info(
                Panel(llm_context, border_style="green", title="供LLM使用的上下文")
            )

    # 步骤6：测试重排序
    logger.info("\n" + "=" * 70)
    logger.info("\n步骤6: 测试重排序功能")

    query = test_queries[0]
    logger.info(f"\n查询: {query}")

    # 先检索更多结果
    initial_results = retriever.retrieve_semantic(query, top_k=5)
    Retriever.display_results(initial_results, title="初步检索结果 (Top-5)")

    # 重排序
    reranked_results = Retriever.rerank_results(initial_results, query, top_k=3)
    Retriever.display_results(reranked_results, title="重排序后 (Top-3)")

    # 完成
    logger.info("\n" + "=" * 70)
    logger.info("=" * 60)
    vector_store.close()


if __name__ == "__main__":
    demo_retrieval()
