"""
RAG系统 - 文档分块模块
支持多种分块策略，并可视化分块结果
"""

from typing import List
from langchain_core.documents import Document
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,  # 递归分割（推荐）
    CharacterTextSplitter,            # 固定大小分割
)
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import tiktoken

console = Console()


class DocumentChunker:
    """
    文档分块器
    支持多种分块策略
    """

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 100,
        separator: str = "\n\n"
    ):
        """
        初始化分块器

        Args:
            chunk_size: 每个块的字符数（中文推荐500-800）
            chunk_overlap: 相邻块重叠的字符数（推荐chunk_size的10-20%）
            separator: 分割符（默认按段落分）
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separator = separator

    def chunk_documents_recursive(
        self,
        documents: List[Document]
    ) -> List[Document]:
        """
        递归分块（推荐方法）
        先尝试按段落分，不行再按句子，最后按字符

        Args:
            documents: 待分块的Document列表

        Returns:
            分块后的Document列表
        """
        console.print(f"\n[cyan]使用递归分块策略...[/cyan]")
        console.print(f"参数: chunk_size={self.chunk_size}, overlap={self.chunk_overlap}")

        # 创建递归分割器
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,  # 使用字符数计算长度
            separators=[
                "\n\n",  # 优先按段落分（双换行）
                "\n",    # 其次按行分
                "。",    # 中文句号
                "！",    # 中文感叹号
                "？",    # 中文问号
                ".",     # 英文句号
                "!",
                "?",
                " ",     # 空格
                ""       # 最后按字符切
            ]
        )

        # 执行分块
        chunks = text_splitter.split_documents(documents)

        console.print(f"[green]✓ 原始文档数: {len(documents)} → 分块后: {len(chunks)}[/green]")

        return chunks

    def chunk_documents_fixed(
        self,
        documents: List[Document]
    ) -> List[Document]:
        """
        固定大小分块
        简单粗暴，每N个字符切一刀

        Args:
            documents: 待分块的Document列表

        Returns:
            分块后的Document列表
        """
        console.print(f"\n[cyan]使用固定大小分块策略...[/cyan]")
        console.print(f"参数: chunk_size={self.chunk_size}, overlap={self.chunk_overlap}")

        text_splitter = CharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separator=self.separator,
            length_function=len
        )

        chunks = text_splitter.split_documents(documents)

        console.print(f"[green]✓ 原始文档数: {len(documents)} → 分块后: {len(chunks)}[/green]")

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
            console.print("[yellow]没有可分析的分块[/yellow]")
            return

        # 初始化tokenizer（用于计算token数）
        try:
            tokenizer = tiktoken.encoding_for_model("gpt-3.5-turbo")
        except:
            tokenizer = None
            console.print("[yellow]未安装tiktoken，跳过token统计[/yellow]")

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

        console.print("\n")
        console.print(table)

        # 长度分布
        console.print("\n[bold]字符数分布:[/bold]")
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
            console.print(f"{range_name:>12}: {bar} ({count})")

    @staticmethod
    def preview_chunks(chunks: List[Document], num_preview: int = 5):
        """
        预览前N个分块内容

        Args:
            chunks: 分块列表
            num_preview: 预览数量
        """
        console.print(f"\n[bold]前 {num_preview} 个分块预览:[/bold]\n")

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
            console.print(f"[cyan]分块 {i}[/cyan] (来源: {source}, 页码: {page})")
            console.print(f"  字符数: {len(content)}")
            console.print(f"  内容: {preview}\n")


def demo_chunking():
    """
    完整演示：从文档加载到分块
    """
    from document_loader import UniversalDocumentLoader

    console.print(Panel.fit(
        "[bold cyan]RAG系统 - 文档分块演示[/bold cyan]",
        border_style="cyan"
    ))

    # 步骤1：创建测试文档
    console.print("\n[bold]步骤1: 准备测试文档[/bold]")

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

    console.print(f"[green]✓ 已创建测试文档: {test_file}[/green]")
    console.print(f"  字符数: {len(test_content)}")

    # 步骤2：加载文档
    console.print("\n[bold]步骤2: 加载文档[/bold]")
    loader = UniversalDocumentLoader()
    documents = loader.load_document(test_file)

    # 步骤3：测试不同的分块策略
    console.print("\n" + "="*60)
    console.print("[bold]步骤3: 测试不同分块策略[/bold]")
    console.print("="*60)

    # 策略1：小块分割（chunk_size=300）
    console.print("\n[bold yellow]方案A: 小块分割 (size=300, overlap=50)[/bold yellow]")
    chunker_small = DocumentChunker(chunk_size=300, chunk_overlap=50)
    chunks_small = chunker_small.chunk_documents_recursive(documents)
    DocumentChunker.analyze_chunks(chunks_small)
    DocumentChunker.preview_chunks(chunks_small, num_preview=3)

    # 策略2：推荐分割（chunk_size=600）
    console.print("\n" + "="*60)
    console.print("\n[bold green]方案B: 推荐分割 (size=600, overlap=100)[/bold green]")
    chunker_recommended = DocumentChunker(chunk_size=600, chunk_overlap=100)
    chunks_recommended = chunker_recommended.chunk_documents_recursive(documents)
    DocumentChunker.analyze_chunks(chunks_recommended)
    DocumentChunker.preview_chunks(chunks_recommended, num_preview=3)

    # 策略3：大块分割（chunk_size=1000）
    console.print("\n" + "="*60)
    console.print("\n[bold magenta]方案C: 大块分割 (size=1000, overlap=150)[/bold magenta]")
    chunker_large = DocumentChunker(chunk_size=1000, chunk_overlap=150)
    chunks_large = chunker_large.chunk_documents_recursive(documents)
    DocumentChunker.analyze_chunks(chunks_large)
    DocumentChunker.preview_chunks(chunks_large, num_preview=3)

    # 总结
    console.print("\n" + "="*60)
    console.print(Panel.fit(
        "[bold cyan]分块策略对比总结[/bold cyan]\n\n"
        f"小块分割: {len(chunks_small)} 个块 - 检索精度高，但上下文可能不足\n"
        f"推荐分割: {len(chunks_recommended)} 个块 - 平衡精度和上下文 ✓\n"
        f"大块分割: {len(chunks_large)} 个块 - 上下文充足，但可能包含无关信息\n\n"
        "[bold green]对于中文文档，推荐使用 size=600-800, overlap=100[/bold green]",
        border_style="cyan"
    ))


if __name__ == "__main__":
    demo_chunking()
