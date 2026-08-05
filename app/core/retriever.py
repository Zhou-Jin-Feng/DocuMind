"""
RAG系统 - 检索模块
支持多种检索策略：语义检索、混合检索、重排序
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from app.utils.logger import get_logger
from rich.table import Table
from rich.panel import Panel

logger = get_logger(__name__)


@dataclass
class RetrievalResult:
    """
    检索结果数据类
    """
    content: str              # 文档内容
    metadata: Dict            # 元数据
    score: float              # 相似度分数（越小越相似，对于距离；或越大越相似，对于相关性）
    rank: int                 # 排名
    source: str = ""          # 来源文件
    page: int = 0             # 页码

    def __post_init__(self):
        """初始化后处理"""
        if self.metadata:
            self.source = self.metadata.get('source_file', self.metadata.get('source', ''))
            self.page = self.metadata.get('page', 0)


class Retriever:
    """
    检索器
    封装多种检索策略
    """

    def __init__(self, vector_store, embedding_client):
        """
        初始化检索器

        Args:
            vector_store: VectorStore实例
            embedding_client: UniversalEmbeddingClient实例
        """
        self.vector_store = vector_store
        self.embedding_client = embedding_client

        logger.info("检索器初始化完成")

    def retrieve_semantic(
        self,
        query: str,
        top_k: int = 5,
        score_threshold: Optional[float] = None,
        metadata_filter: Optional[Dict] = None
    ) -> List[RetrievalResult]:
        """
        语义检索（基于向量相似度）

        Args:
            query: 查询问题
            top_k: 返回结果数量
            score_threshold: 距离阈值，大于此值的结果会被过滤（可选）
            metadata_filter: 元数据过滤条件（可选）

        Returns:
            检索结果列表
        """
        logger.info(f"\n执行语义检索...")
        logger.info(f"  查询: {query}")
        logger.info(f"  Top-K: {top_k}")

        # 1. 将问题向量化
        try:
            query_embedding = self.embedding_client.embed_text(query)
        except Exception as e:
            logger.info(f"向量化失败: {str(e)}")
            return []

        # 2. 在向量库中搜索
        try:
            search_results = self.vector_store.search(
                query_embedding=query_embedding,
                n_results=top_k,
                where=metadata_filter
            )
        except Exception as e:
            logger.info(f"搜索失败: {str(e)}")
            return []

        # 3. 构造结果对象
        results = []

        for i, (doc, meta, dist) in enumerate(
            zip(
                search_results['documents'],
                search_results['metadatas'],
                search_results['distances']
            )
        ):
            # 应用距离阈值过滤
            if score_threshold is not None and dist > score_threshold:
                continue

            result = RetrievalResult(
                content=doc,
                metadata=meta,
                score=dist,  # ChromaDB返回的是距离（越小越好）
                rank=i + 1
            )
            results.append(result)

        logger.info(f"检索到 {len(results)} 个结果")

        return results

    def retrieve_with_context(
        self,
        query: str,
        top_k: int = 5,
        expand_context: bool = False
    ) -> List[RetrievalResult]:
        """
        带上下文扩展的检索
        检索到相关块后，可选地包含其前后块（提供更完整的上下文）

        Args:
            query: 查询问题
            top_k: 返回结果数量
            expand_context: 是否扩展上下文（包含相邻块）

        Returns:
            检索结果列表
        """
        # 先执行标准检索
        results = self.retrieve_semantic(query, top_k)

        if not expand_context:
            return results

        # TODO: 实现上下文扩展逻辑
        # 需要在存储时记录chunk_index，然后检索相邻块
        logger.info("上下文扩展功能待实现（需要存储时添加chunk_index）")

        return results

    @staticmethod
    def rerank_results(
        results: List[RetrievalResult],
        query: str,
        top_k: int = 3
    ) -> List[RetrievalResult]:
        """
        重排序（简化版）
        使用启发式规则对结果重新排序

        Args:
            results: 初步检索结果
            query: 查询问题
            top_k: 重排序后保留的数量

        Returns:
            重排序后的结果
        """
        logger.info(f"\n执行重排序...")
        logger.info(f"  初始结果数: {len(results)}")

        if not results:
            return []

        # 简化版重排序：结合距离和关键词匹配
        query_terms = set(query.lower().split())

        for result in results:
            # 计算关键词匹配度
            content_terms = set(result.content.lower().split())
            keyword_overlap = len(query_terms & content_terms) / len(query_terms)

            # 综合得分（距离越小越好，重叠越大越好）
            # 归一化到0-1，越大越好
            distance_score = 1 / (1 + result.score)  # 将距离转为相似度
            combined_score = 0.7 * distance_score + 0.3 * keyword_overlap

            result.score = combined_score

        # 按综合得分降序排序
        reranked = sorted(results, key=lambda x: x.score, reverse=True)

        # 更新排名
        for i, result in enumerate(reranked[:top_k], 1):
            result.rank = i

        logger.info(f"重排序完成，保留前 {top_k} 个结果")

        return reranked[:top_k]

    @staticmethod
    def format_results_for_llm(results: List[RetrievalResult]) -> str:
        """
        将检索结果格式化为LLM的上下文

        Args:
            results: 检索结果列表

        Returns:
            格式化的上下文字符串
        """
        if not results:
            return "未找到相关信息。"

        context_parts = []

        for i, result in enumerate(results, 1):
            context_parts.append(
                f"[文档{i}] 来源: {result.source or '未知'}\n"
                f"{result.content}\n"
            )

        return "\n".join(context_parts)

    @staticmethod
    def display_results(results: List[RetrievalResult], title: str = "检索结果"):
        """
        美化显示检索结果

        Args:
            results: 检索结果列表
            title: 显示标题
        """
        if not results:
            logger.info("没有检索到相关结果")
            return

        logger.info(f"\n{title} (共 {len(results)} 个)\n")

        for result in results:
            # 限制显示长度
            content_preview = result.content[:150].replace('\n', ' ')
            if len(result.content) > 150:
                content_preview += "..."

            logger.info(f"排名 {result.rank} (得分: {result.score:.4f})")
            logger.info(f"  来源: {result.source or '未知'} | 页码: {result.page or 'N/A'}")
            logger.info(f"  内容: {content_preview}\n")


def demo_retrieval():
    """
    演示：完整的检索流程
    """
    logger.info("="*60)

    # 导入依赖模块
    try:
        from vector_store import VectorStore
        from embedding_client import UniversalEmbeddingClient
        from document_loader import UniversalDocumentLoader
        from document_chunker import DocumentChunker
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


