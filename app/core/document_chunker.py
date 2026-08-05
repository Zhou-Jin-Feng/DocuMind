"""
RAG 系统文档分块模块。

支持递归分块和固定分块，并为每个 Chunk 补充稳定元数据。
"""

import hashlib
from collections import defaultdict
from typing import List

import tiktoken
from langchain_core.documents import Document
from langchain_text_splitters import CharacterTextSplitter, RecursiveCharacterTextSplitter
from rich.panel import Panel
from rich.table import Table

from app.utils.logger import get_logger

logger = get_logger(__name__)


class DocumentChunker:
    """文档分块器。"""

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 100,
        separator: str = "\n\n",
    ):
        if chunk_size <= 0:
            raise ValueError("chunk_size 必须大于 0")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap 不能小于 0")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap 必须小于 chunk_size")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separator = separator

    @staticmethod
    def _ensure_document_ids(documents: List[Document]) -> None:
        """为手工构造的 Document 补充稳定 document_id。"""
        for document in documents:
            if document.metadata.get("document_id"):
                continue
            source = str(document.metadata.get("source_file") or document.metadata.get("source") or "unknown")
            page = str(document.metadata.get("page_number") or document.metadata.get("page") or "")
            payload = f"{source}\0{page}\0{document.page_content}".encode("utf-8")
            document.metadata["document_id"] = hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _decorate_chunks(chunks: List[Document]) -> List[Document]:
        """去除空 Chunk，并增加 chunk_index、chunk_id 和字符数。"""
        counters: defaultdict[str, int] = defaultdict(int)
        decorated: List[Document] = []

        for chunk in chunks:
            content = chunk.page_content.strip()
            if not content:
                continue
            chunk.page_content = content

            document_id = str(chunk.metadata["document_id"])
            chunk_index = counters[document_id]
            counters[document_id] += 1
            page_number = chunk.metadata.get("page_number", "")
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            chunk_id = hashlib.sha256(
                f"{document_id}:{page_number}:{chunk_index}:{content_hash}".encode("utf-8")
            ).hexdigest()

            chunk.metadata["chunk_index"] = chunk_index
            chunk.metadata["chunk_id"] = chunk_id
            chunk.metadata["chunk_char_count"] = len(content)
            decorated.append(chunk)

        return decorated

    def chunk_documents_recursive(self, documents: List[Document]) -> List[Document]:
        """优先按段落和句子边界进行递归分块。"""
        if not documents:
            return []

        self._ensure_document_ids(documents)
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""],
        )
        chunks = self._decorate_chunks(text_splitter.split_documents(documents))
        logger.info(
            f"递归分块完成: 原始文档={len(documents)}, chunks={len(chunks)}, "
            f"chunk_size={self.chunk_size}, overlap={self.chunk_overlap}"
        )
        return chunks

    def chunk_documents_fixed(self, documents: List[Document]) -> List[Document]:
        """按固定大小进行分块。"""
        if not documents:
            return []

        self._ensure_document_ids(documents)
        text_splitter = CharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separator=self.separator,
            length_function=len,
        )
        chunks = self._decorate_chunks(text_splitter.split_documents(documents))
        logger.info(
            f"固定分块完成: 原始文档={len(documents)}, chunks={len(chunks)}, "
            f"chunk_size={self.chunk_size}, overlap={self.chunk_overlap}"
        )
        return chunks

    @staticmethod
    def analyze_chunks(chunks: List[Document]):
        """
        分析分块结果
        统计每个块的长度、token数等信息

        Args:
            chunks: 分块后的Document列表
        """
        if not chunks:
            logger.info("没有可分析的分块")
            return

        # 初始化tokenizer（用于计算token数）
        try:
            tokenizer = tiktoken.encoding_for_model("gpt-3.5-turbo")
        except:
            tokenizer = None
            logger.info("未安装tiktoken，跳过token统计")

        # 统计信息
        chunk_lengths = [len(chunk.page_content) for chunk in chunks]
        avg_length = sum(chunk_lengths) / len(chunk_lengths)
        min_length = min(chunk_lengths)
        max_length = max(chunk_lengths)

        if tokenizer:
            chunk_tokens = [
                len(tokenizer.encode(chunk.page_content))
                for chunk in chunks
            ]
            avg_tokens = sum(chunk_tokens) / len(chunk_tokens)
            total_tokens = sum(chunk_tokens)
        else:
            avg_tokens = 0
            total_tokens = 0

        # 创建摘要表格
        table = Table(title="分块统计摘要", show_header=True, header_style="bold magenta")
        table.add_column("指标", style="cyan", width=20)
        table.add_column("数值", style="green", width=30)

        table.add_row("总分块数", str(len(chunks)))
        table.add_row("平均字符数", f"{avg_length:.0f}")
        table.add_row("最小字符数", str(min_length))
        table.add_row("最大字符数", str(max_length))

        if tokenizer:
            table.add_row("平均Token数", f"{avg_tokens:.0f}")
            table.add_row("总Token数", f"{total_tokens:,}")

        logger.info("\n")
        logger.info(table)

        # 长度分布
        logger.info("\n字符数分布:")
        distribution = {
            "0-200": 0,
            "201-400": 0,
            "401-600": 0,
            "601-800": 0,
            "801-1000": 0,
            "1000+": 0
        }

        for length in chunk_lengths:
            if length <= 200:
                distribution["0-200"] += 1
            elif length <= 400:
                distribution["201-400"] += 1
            elif length <= 600:
                distribution["401-600"] += 1
            elif length <= 800:
                distribution["601-800"] += 1
            elif length <= 1000:
                distribution["801-1000"] += 1
            else:
                distribution["1000+"] += 1

        for range_name, count in distribution.items():
            bar = "█" * (count * 2) if count > 0 else ""
            logger.info(f"{range_name:>12}: {bar} ({count})")

    @staticmethod
    def preview_chunks(chunks: List[Document], num_preview: int = 5):
        """
        预览前N个分块内容

        Args:
            chunks: 分块列表
            num_preview: 预览数量
        """
        logger.info(f"\n前 {num_preview} 个分块预览:\n")

        for i, chunk in enumerate(chunks[:num_preview], 1):
            # 获取元数据
            source = chunk.metadata.get('source_file', 'Unknown')
            page = chunk.metadata.get('page', 'N/A')

            # 内容预览（最多显示150字符）
            content = chunk.page_content.strip()
            preview = content[:150].replace('\n', ' ')

            if len(content) > 150:
                preview += "..."

            # 打印
            logger.info(f"分块 {i} (来源: {source}, 页码: {page})")
            logger.info(f"  字符数: {len(content)}")
            logger.info(f"  内容: {preview}\n")


def demo_chunking():
    """
    完整演示：从文档加载到分块
    """
    from app.core.document_loader import UniversalDocumentLoader

    logger.info("="*60)

    # 步骤1：创建测试文档
    logger.info("\n步骤1: 准备测试文档")

    test_content = """
人工智能技术发展报告

第一章：人工智能概述
人工智能（Artificial Intelligence, AI）是计算机科学的一个分支，致力于创建能够模拟人类智能的系统。这些系统可以学习、推理、解决问题，并做出决策。

AI的历史可以追溯到20世纪50年代。1956年，约翰·麦卡锡首次提出"人工智能"这个术语。从那时起，AI经历了多次发展浪潮和低谷期。

第二章：机器学习基础
机器学习是AI的核心技术之一。它使计算机系统能够从数据中学习，而无需明确编程。机器学习主要分为三类：监督学习、无监督学习和强化学习。

监督学习使用标记的训练数据。算法学习输入和输出之间的映射关系。常见应用包括图像分类、语音识别等。

无监督学习处理未标记的数据。算法试图发现数据中的隐藏模式或结构。聚类和降维是典型的无监督学习任务。

强化学习通过与环境交互来学习。智能体通过试错来最大化累积奖励。AlphaGo就是强化学习的成功案例。

第三章：深度学习革命
深度学习是机器学习的一个子领域，使用多层神经网络。2012年，AlexNet在ImageNet竞赛中取得突破，标志着深度学习时代的开启。

卷积神经网络（CNN）在计算机视觉领域表现出色。它们能够自动学习图像的层次化特征表示。

循环神经网络（RNN）擅长处理序列数据。长短期记忆网络（LSTM）解决了传统RNN的梯度消失问题。

Transformer架构彻底改变了自然语言处理。它使用注意力机制，能够并行处理序列数据。BERT和GPT系列模型都基于Transformer。

第四章：RAG技术详解
检索增强生成（RAG）结合了信息检索和文本生成。它让大语言模型能够访问外部知识库，从而生成更准确、更及时的回答。

RAG的工作流程包括：文档加载、文本分块、向量化、检索和生成。每个步骤都至关重要。

文本分块是RAG系统的关键环节。合适的分块大小能够平衡上下文完整性和检索精度。推荐的chunk_size在500-800字符之间。

向量数据库用于高效存储和检索向量。常见的向量数据库包括ChromaDB、Pinecone和Weaviate。

第五章：未来展望
AI技术正在快速发展。多模态模型能够同时处理文本、图像和音频。具身智能将AI带入物理世界。

AI的伦理和安全问题日益重要。我们需要确保AI系统的公平性、透明度和可控性。

通用人工智能（AGI）仍然是终极目标。尽管当前的AI系统在特定任务上表现出色，但距离真正的通用智能还有很长的路要走。
    """.strip()

    # 创建测试文件
    test_file = "test_chunking_document.txt"
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write(test_content)

    logger.info(f"已创建测试文档: {test_file}")
    logger.info(f"  字符数: {len(test_content)}")

    # 步骤2：加载文档
    logger.info("\n步骤2: 加载文档")
    loader = UniversalDocumentLoader()
    documents = loader.load_document(test_file)

    # 步骤3：测试不同的分块策略
    logger.info("\n" + "="*60)
    logger.info("步骤3: 测试不同分块策略")
    logger.info("="*60)

    # 策略1：小块分割（chunk_size=300）
    logger.info("\n方案A: 小块分割 (size=300, overlap=50)")
    chunker_small = DocumentChunker(chunk_size=300, chunk_overlap=50)
    chunks_small = chunker_small.chunk_documents_recursive(documents)
    DocumentChunker.analyze_chunks(chunks_small)
    DocumentChunker.preview_chunks(chunks_small, num_preview=3)

    # 策略2：推荐分割（chunk_size=600）
    logger.info("\n" + "="*60)
    logger.info("\n方案B: 推荐分割 (size=600, overlap=100)")
    chunker_recommended = DocumentChunker(chunk_size=600, chunk_overlap=100)
    chunks_recommended = chunker_recommended.chunk_documents_recursive(documents)
    DocumentChunker.analyze_chunks(chunks_recommended)
    DocumentChunker.preview_chunks(chunks_recommended, num_preview=3)

    # 策略3：大块分割（chunk_size=1000）
    logger.info("\n" + "="*60)
    logger.info("\n方案C: 大块分割 (size=1000, overlap=150)")
    chunker_large = DocumentChunker(chunk_size=1000, chunk_overlap=150)
    chunks_large = chunker_large.chunk_documents_recursive(documents)
    DocumentChunker.analyze_chunks(chunks_large)
    DocumentChunker.preview_chunks(chunks_large, num_preview=3)

    # 总结
    logger.info("\n" + "="*60)
    logger.info(Panel.fit(
        "[bold cyan]分块策略对比总结[/bold cyan]\n\n"
        f"小块分割: {len(chunks_small)} 个块 - 检索精度高，但上下文可能不足\n"
        f"推荐分割: {len(chunks_recommended)} 个块 - 平衡精度和上下文 ✓\n"
        f"大块分割: {len(chunks_large)} 个块 - 上下文充足，但可能包含无关信息\n\n"
        "[bold green]对于中文文档，推荐使用 size=600-800, overlap=100[/bold green]",
        border_style="cyan"
    ))


if __name__ == "__main__":
    demo_chunking()


