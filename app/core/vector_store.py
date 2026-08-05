"""
RAG系统 - 向量数据库存储模块
基于ChromaDB实现向量的增删改查
"""

import os
import uuid
from typing import List, Dict, Optional
from langchain_core.documents import Document
import chromadb
from chromadb.config import Settings
from app.utils.logger import get_logger
from rich.table import Table
from rich.panel import Panel

logger = get_logger(__name__)


class VectorStore:
    """
    向量存储管理器
    封装ChromaDB的基本操作
    """

    def __init__(
        self,
        collection_name: str = "rag_documents",
        persist_directory: str = "./chroma_db"
    ):
        """
        初始化向量存储

        Args:
            collection_name: 集合名称（类似数据库表名）
            persist_directory: 数据持久化目录
        """
        self.collection_name = collection_name
        self.persist_directory = persist_directory

        # 创建存储目录
        os.makedirs(persist_directory, exist_ok=True)

        # 初始化ChromaDB客户端
        logger.info(f"正在初始化向量数据库...")

        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(
                anonymized_telemetry=False,  # 关闭匿名遥测
            )
        )

        # 创建或获取集合
        try:
            self.collection = self.client.get_collection(name=collection_name)
            logger.info(f"已连接到现有集合: {collection_name}")
            logger.info(f"  当前文档数: {self.collection.count()}")
        except:
            self.collection = self.client.create_collection(
                name=collection_name,
                metadata={"description": "RAG系统文档向量存储"}
            )
            logger.info(f"已创建新集合: {collection_name}")

        logger.info(f"  存储路径: {persist_directory}\n")

    def add_documents(
        self,
        documents: List[Document],
        embeddings: List[List[float]],
        ids: Optional[List[str]] = None
    ) -> List[str]:
        """
        添加文档到向量数据库

        Args:
            documents: LangChain Document对象列表
            embeddings: 对应的向量列表
            ids: 可选的文档ID列表（不提供则自动生成）

        Returns:
            文档ID列表
        """
        if len(documents) != len(embeddings):
            raise ValueError(
                f"文档数量({len(documents)})与向量数量({len(embeddings)})不匹配"
            )

        # 生成ID（如果未提供）
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in range(len(documents))]

        # 提取文本和元数据
        texts = [doc.page_content for doc in documents]
        metadatas = [doc.metadata for doc in documents]

        # 添加到数据库
        logger.info(f"正在添加 {len(documents)} 个文档到向量库...")

        try:
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas
            )

            logger.info(f"成功添加 {len(documents)} 个文档")
            logger.info(f"  当前总文档数: {self.collection.count()}")

            return ids

        except Exception as e:
            logger.info(f"添加失败: {str(e)}")
            raise

    def search(
        self,
        query_embedding: List[float],
        n_results: int = 5,
        where: Optional[Dict] = None
    ) -> Dict:
        """
        向量相似度搜索

        Args:
            query_embedding: 查询向量
            n_results: 返回的结果数量
            where: 元数据过滤条件（例如 {"source_file": "报告.pdf"}）

        Returns:
            检索结果字典，包含ids、documents、metadatas、distances
        """
        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where
            )

            # 展平结果（query返回的是嵌套列表）
            return {
                'ids': results['ids'][0] if results['ids'] else [],
                'documents': results['documents'][0] if results['documents'] else [],
                'metadatas': results['metadatas'][0] if results['metadatas'] else [],
                'distances': results['distances'][0] if results['distances'] else []
            }

        except Exception as e:
            logger.info(f"搜索失败: {str(e)}")
            raise

    def delete_by_ids(self, ids: List[str]) -> None:
        """
        根据ID删除文档

        Args:
            ids: 要删除的文档ID列表
        """
        try:
            self.collection.delete(ids=ids)
            logger.info(f"已删除 {len(ids)} 个文档")
        except Exception as e:
            logger.info(f"删除失败: {str(e)}")
            raise

    def delete_collection(self) -> None:
        """
        删除整个集合（慎用！）
        """
        try:
            self.client.delete_collection(name=self.collection_name)
            logger.info(f"已删除集合: {self.collection_name}")
        except Exception as e:
            logger.info(f"删除集合失败: {str(e)}")
            raise

    def get_collection_info(self) -> Dict:
        """
        获取集合信息
        """
        count = self.collection.count()
        metadata = self.collection.metadata

        return {
            'name': self.collection_name,
            'count': count,
            'metadata': metadata
        }

    def peek_documents(self, limit: int = 5) -> Dict:
        """
        查看前N个文档（用于调试）

        Args:
            limit: 查看数量

        Returns:
            文档字典
        """
        try:
            results = self.collection.peek(limit=limit)
            return results
        except Exception as e:
            logger.info(f"查看失败: {str(e)}")
            raise


def demo_basic_operations():
    """
    演示：向量数据库基本操作
    """
    logger.info("="*60)

    # 步骤1：初始化向量存储
    logger.info("\n步骤1: 初始化向量存储")
    store = VectorStore(
        collection_name="demo_collection",
        persist_directory="./demo_chroma_db"
    )

    # 步骤2：准备测试数据
    logger.info("\n步骤2: 准备测试数据")

    test_documents = [
        Document(
            page_content="机器学习是人工智能的核心技术，通过算法让计算机从数据中学习。",
        ),
        Document(
            page_content="深度学习使用多层神经网络，在图像识别和自然语言处理中表现出色。",
        ),
        Document(
            page_content="RAG技术结合了检索和生成，让大语言模型能够访问外部知识库。",
            metadata={"source": "RAG指南.pdf", "page": 1, "topic": "RAG"}
        ),
        Document(
            page_content="向量数据库专门用于存储和检索高维向量，支持快速相似度搜索。",
            metadata={"source": "向量数据库.pdf", "page": 1, "topic": "向量数据库"}
        ),
    ]

    logger.info(f"准备了 {len(test_documents)} 个测试文档")

    # 步骤3：生成向量（这里用模拟向量）
    logger.info("\n步骤3: 生成向量（模拟）")

    # 实际应用中应该用embedding_client.py生成真实向量
    # 这里为了演示，生成随机向量
    import random
    test_embeddings = [
        [random.random() for _ in range(1536)]
        for _ in range(len(test_documents))
    ]

    logger.info(f"生成了 {len(test_embeddings)} 个向量（每个1536维）")

    # 步骤4：添加到向量库
    logger.info("\n步骤4: 添加文档到向量库")
    doc_ids = store.add_documents(test_documents, test_embeddings)

    logger.info(f"\n文档ID: {doc_ids[:2]}... (共{len(doc_ids)}个)")

    # 步骤5：查看集合信息
    logger.info("\n步骤5: 查看集合信息")
    info = store.get_collection_info()

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("属性", width=20)
    table.add_column("值", width=40)

    table.add_row("集合名称", info['name'])
    table.add_row("文档数量", str(info['count']))

    logger.info(table)

    # 步骤6：预览文档
    logger.info("\n步骤6: 预览前3个文档\n")
    peek_results = store.peek_documents(limit=3)

    for i, (doc, meta) in enumerate(zip(peek_results['documents'], peek_results['metadatas']), 1):
        logger.info(f"文档 {i}:")
        logger.info(f"  内容: {doc[:50]}...")
        logger.info(f"  来源: {meta.get('source', 'N/A')}")
        logger.info(f"  主题: {meta.get('topic', 'N/A')}\n")

    # 步骤7：相似度搜索
    logger.info("\n步骤7: 执行相似度搜索")

    # 用第一个文档的向量作为查询（实际应该用新问题的向量）
    query_vector = test_embeddings[0]

    logger.info("查询向量: 机器学习相关内容")
    results = store.search(query_vector, n_results=3)

    logger.info(f"\n找到 {len(results['documents'])} 个相关文档:\n")

    for i, (doc, meta, dist) in enumerate(
        zip(results['documents'], results['metadatas'], results['distances']), 1
    ):
        logger.info(f"结果 {i}: (相似度距离: {dist:.4f})")
        logger.info(f"  内容: {doc[:60]}...")
        logger.info(f"  来源: {meta.get('source', 'N/A')}\n")

    # 步骤8：元数据过滤搜索
    logger.info("\n步骤8: 带元数据过滤的搜索")

    filtered_results = store.search(
        query_vector,
        n_results=3,
    )

    logger.info(f"\n找到 {len(filtered_results['documents'])} 个匹配文档:\n")

    for i, (doc, meta) in enumerate(
        zip(filtered_results['documents'], filtered_results['metadatas']), 1
    ):
        logger.info(f"结果 {i}:")
        logger.info(f"  内容: {doc[:60]}...")
        logger.info(f"  来源: {meta.get('source', 'N/A')}\n")

    # 完成
    logger.info("="*60)


def demo_integration_with_real_embeddings():
    """
    演示：与真实嵌入模型集成
    """
    logger.info("="*60)

    # 导入前面的模块
    try:
        from document_loader import UniversalDocumentLoader
        from document_chunker import DocumentChunker
        from embedding_client import UniversalEmbeddingClient
    except ImportError as e:
        logger.info(f"导入失败: {str(e)}")
        logger.info("请确保前面课程的脚本都在同一目录")
        return

    # 步骤1：创建测试文档
    logger.info("\n步骤1: 创建测试文档")

    test_content = """
向量数据库技术指南

第一章：向量数据库简介
向量数据库是专门用于存储和检索高维向量的数据库系统。它在RAG、推荐系统、图像搜索等场景中发挥重要作用。

第二章：ChromaDB使用
ChromaDB是一个轻量级的嵌入式向量数据库，支持持久化存储和快速检索。它特别适合中小型项目和学习场景。

第三章：检索优化
合理设置chunk_size和使用元数据过滤可以显著提升检索精度。建议根据具体场景进行实验调优。
    """.strip()

    test_file = "test_vector_store.txt"
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write(test_content)

    logger.info(f"已创建测试文档: {test_file}")

    # 步骤2：加载文档
    logger.info("\n步骤2: 加载文档")
    loader = UniversalDocumentLoader()
    documents = loader.load_document(test_file)

    # 步骤3：分块
    logger.info("\n步骤3: 文档分块")
    chunker = DocumentChunker(chunk_size=200, chunk_overlap=50)
    chunks = chunker.chunk_documents_recursive(documents)

    logger.info(f"分块结果: {len(chunks)} 个块")

    # 步骤4：向量化
    logger.info("\n步骤4: 向量化文档块")

    try:
        # 尝试使用配置的嵌入模型
        provider = os.getenv('DEFAULT_EMBEDDING_PROVIDER', 'openai')
        logger.info(f"使用嵌入模型: {provider}")

        embedding_client = UniversalEmbeddingClient(provider)

        # 提取文本
        texts = [chunk.page_content for chunk in chunks]

        # 批量向量化
        embeddings = embedding_client.embed_texts_batch(texts, show_progress=True)

    except Exception as e:
        logger.info(f"向量化失败: {str(e)}")
        logger.info("使用模拟向量继续演示...")

        # 使用模拟向量
        import random
        embeddings = [[random.random() for _ in range(1536)] for _ in chunks]

    # 步骤5：存储到向量库
    logger.info("\n步骤5: 存储到向量数据库")

    store = VectorStore(
        collection_name="integrated_demo",
        persist_directory="./integrated_chroma_db"
    )

    doc_ids = store.add_documents(chunks, embeddings)

    # 步骤6：测试检索
    logger.info("\n步骤6: 测试检索功能")

    test_query = "ChromaDB是什么？"
    logger.info(f"\n查询问题: {test_query}")

    try:
        # 向量化查询
        query_embedding = embedding_client.embed_text(test_query)
    except:
        # 使用模拟向量
        query_embedding = embeddings[1]  # 用第2个块的向量

    # 检索
    results = store.search(query_embedding, n_results=2)

    logger.info(f"\n检索到 {len(results['documents'])} 个相关片段:\n")

    for i, (doc, meta, dist) in enumerate(
        zip(results['documents'], results['metadatas'], results['distances']), 1
    ):
        logger.info(f"片段 {i}: (距离: {dist:.4f})")
        logger.info(f"  {doc}\n")

    logger.info("="*60)


if __name__ == "__main__":
    logger.info("\nRAG系统 - 向量数据库存储模块测试\n")

    logger.info("选择演示模式:")
    logger.info("1. 基本操作演示（增删改查）")
    logger.info("2. 完整流程演示（文档→分块→向量化→存储）")

    choice = input("\n请输入选项 (1/2): ").strip()

    if choice == "1":
        demo_basic_operations()
    else:
        demo_integration_with_real_embeddings()


