"""
RAG 系统检索模块。

明确区分 Chroma 距离和重排分数，并保留检索异常语义。
"""

import re
from dataclasses import dataclass
from time import perf_counter
from typing import Callable, Dict, List, Optional

from rich.panel import Panel

from app.observability.metrics import get_metrics
from app.observability.tracing import trace_span
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RetrievalResult:
    """单条检索结果。distance 越小越相关，rerank_score 越大越相关。"""

    content: str
    metadata: Dict
    distance: float
    rank: int
    source: str = ""
    page_number: Optional[int] = None
    rerank_score: Optional[float] = None

    def __post_init__(self) -> None:
        self.metadata = self.metadata or {}
        self.source = str(
            self.metadata.get("source_file") or self.metadata.get("source") or self.source
        )
        page = self.metadata.get("page_number")
        if isinstance(page, int) and page > 0:
            self.page_number = page

    @property
    def page(self) -> int:
        """兼容旧调用；无页码时返回 0。"""
        return self.page_number or 0


class Retriever:
    """封装语义检索和轻量重排。"""

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
        """执行语义检索；score_threshold 表示允许的最大距离。"""
        normalized_query = (query or "").strip()
        if not normalized_query:
            raise ValueError("查询内容不能为空")
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")
        if score_threshold is not None and score_threshold < 0:
            raise ValueError("score_threshold 不能小于 0")

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
                    query_embedding = self.embedding_client.embed_text(
                        normalized_query
                    )
            except Exception as exc:
                embedding_duration = perf_counter() - embedding_started
                retrieval_duration = perf_counter() - retrieval_started
                metrics.observe_embedding(
                    provider, "embedding.query", "error", embedding_duration
                )
                metrics.observe_retrieval(
                    provider, "error", retrieval_duration
                )
                metrics.record_component_error(
                    "embedding.query", type(exc).__name__
                )
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
                    search_results = self.vector_store.search(
                        query_embedding=query_embedding,
                        n_results=(max(top_k * 5, top_k) if result_predicate else top_k),
                        where=metadata_filter,
                    )
            except Exception as exc:
                search_duration = perf_counter() - search_started
                retrieval_duration = perf_counter() - retrieval_started
                metrics.observe_retrieval(
                    provider, "error", retrieval_duration
                )
                metrics.record_component_error(
                    "vector.search", type(exc).__name__
                )
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
                if result_predicate is not None and not result_predicate(metadata or {}):
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
            terms.update(sequence[index : index + 2] for index in range(len(sequence) - 1))
        return terms

    @staticmethod
    def rerank_results(
        results: List[RetrievalResult],
        query: str,
        top_k: int = 3,
    ) -> List[RetrievalResult]:
        """结合向量距离和轻量关键词覆盖率进行重排。"""
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")
        if not results:
            return []

        query_terms = Retriever._keyword_terms(query)
        for result in results:
            content_terms = Retriever._keyword_terms(result.content)
            keyword_overlap = (
                len(query_terms & content_terms) / len(query_terms) if query_terms else 0.0
            )
            distance_similarity = 1 / (1 + max(result.distance, 0.0))
            result.rerank_score = 0.7 * distance_similarity + 0.3 * keyword_overlap

        reranked = sorted(
            results,
            key=lambda result: result.rerank_score if result.rerank_score is not None else -1.0,
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
    def display_results(results: List[RetrievalResult], title: str = "检索结果") -> None:
        """以普通日志输出检索结果摘要。"""
        logger.info(f"{title}: {len(results)} 条")
        for result in results:
            rerank = (
                f", rerank={result.rerank_score:.4f}"
                if result.rerank_score is not None
                else ""
            )
            logger.info(
                f"排名 {result.rank}: distance={result.distance:.4f}{rerank}, "
                f"source={result.source or '未知'}"
            )

def demo_retrieval():
    """
    演示：完整的检索流程
    """
    logger.info("="*60)

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
    with open(kb_file, 'w', encoding='utf-8') as f:
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
        provider = os.getenv('DEFAULT_EMBEDDING_PROVIDER', 'openai')
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
        persist_directory="./retrieval_chroma_db"
    )

    vector_store.add_documents(chunks, embeddings)

    # 步骤4：初始化检索器
    logger.info("\n步骤4: 初始化检索器")

    if embedding_client is None:
        logger.info("模拟模式，无法测试真实检索")
        return

    retriever = Retriever(vector_store, embedding_client)

    # 步骤5：测试不同的查询
    logger.info("\n" + "="*70)
    logger.info("\n步骤5: 测试检索功能")

    test_queries = [
        "监督学习有哪些常见算法？",
        "深度学习和机器学习的区别",
        "RAG系统包含哪些组件？",
    ]

    for i, query in enumerate(test_queries, 1):
        logger.info("\n" + "="*70)
        logger.info(f"\n查询 {i}: {query}")

        # 执行检索
        results = retriever.retrieve_semantic(query, top_k=3)

        # 显示结果
        Retriever.display_results(results, title=f"语义检索结果 - 查询{i}")

        # 格式化为LLM上下文
        if i == 1:  # 只在第一个查询展示上下文格式
            logger.info("\n格式化为LLM上下文:")
            llm_context = Retriever.format_results_for_llm(results[:2])
            logger.info(Panel(llm_context, border_style="green", title="供LLM使用的上下文"))

    # 步骤6：测试重排序
    logger.info("\n" + "="*70)
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
    logger.info("\n" + "="*70)
    logger.info("="*60)


if __name__ == "__main__":
    demo_retrieval()
