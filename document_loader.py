"""
RAG系统 - 文档加载模块
支持PDF、Word、TXT三种格式的统一加载
"""

import os
from typing import List
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

# LangChain文档加载器
from langchain_community.document_loaders import (
    PyPDFLoader,        # PDF加载器
    Docx2txtLoader,     # Word加载器
    TextLoader,         # TXT加载器
)
from langchain_core.documents import Document

console = Console()


class UniversalDocumentLoader:
    """
    通用文档加载器
    自动识别文件类型并选择合适的加载器
    """

    # 支持的文件格式及对应的加载器
    LOADERS = {
        '.pdf': PyPDFLoader,
        '.docx': Docx2txtLoader,
        '.doc': Docx2txtLoader,  # 老版Word格式
        '.txt': TextLoader,
    }

    def __init__(self):
        self.console = Console()

    def load_document(self, file_path: str) -> List[Document]:
        """
        加载单个文档

        Args:
            file_path: 文档路径

        Returns:
            Document对象列表（每个对象包含文本+元数据）
        """
        # 检查文件是否存在
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        # 获取文件扩展名
        file_ext = Path(file_path).suffix.lower()

        # 检查是否支持该格式
        if file_ext not in self.LOADERS:
            raise ValueError(
                f"不支持的文件格式: {file_ext}\n"
                f"目前支持: {', '.join(self.LOADERS.keys())}"
            )

        # 选择对应的加载器
        loader_class = self.LOADERS[file_ext]

        try:
            console.print(f"[cyan]正在加载 {file_ext} 文件...[/cyan]")

            # 实例化加载器
            if file_ext == '.txt':
                # TXT需要指定编码（中文通常是UTF-8或GBK）
                loader = loader_class(file_path, encoding='utf-8')
            else:
                loader = loader_class(file_path)

            # 加载文档
            documents = loader.load()

            # 添加文件名到元数据
            for doc in documents:
                doc.metadata['source_file'] = Path(file_path).name
                doc.metadata['file_type'] = file_ext

            console.print(f"[green]✓ 成功加载 {len(documents)} 个文档片段[/green]")

            return documents

        except UnicodeDecodeError:
            # TXT文件编码错误，尝试GBK
            console.print("[yellow]UTF-8解码失败，尝试GBK编码...[/yellow]")
            loader = TextLoader(file_path, encoding='gbk')
            documents = loader.load()

            for doc in documents:
                doc.metadata['source_file'] = Path(file_path).name
                doc.metadata['file_type'] = file_ext

            console.print(f"[green]✓ 成功加载 {len(documents)} 个文档片段[/green]")
            return documents

        except Exception as e:
            console.print(f"[red]✗ 加载失败: {str(e)}[/red]")
            raise

    def load_directory(self, dir_path: str) -> List[Document]:
        """
        批量加载目录下的所有文档

        Args:
            dir_path: 目录路径

        Returns:
            所有文档的Document对象列表
        """
        if not os.path.isdir(dir_path):
            raise NotADirectoryError(f"不是有效的目录: {dir_path}")

        all_documents = []
        supported_files = []

        # 扫描目录
        for file_name in os.listdir(dir_path):
            file_path = os.path.join(dir_path, file_name)
            file_ext = Path(file_path).suffix.lower()

            if file_ext in self.LOADERS and os.path.isfile(file_path):
                supported_files.append(file_path)

        if not supported_files:
            console.print(f"[yellow]⚠ 目录中没有找到支持的文档[/yellow]")
            return []

        console.print(f"\n[cyan]找到 {len(supported_files)} 个文档，开始加载...[/cyan]\n")

        # 逐个加载
        for file_path in supported_files:
            try:
                docs = self.load_document(file_path)
                all_documents.extend(docs)
            except Exception as e:
                console.print(f"[red]跳过文件 {Path(file_path).name}: {str(e)}[/red]")

        console.print(f"\n[green]✓ 总共加载 {len(all_documents)} 个文档片段[/green]")

        return all_documents

    @staticmethod
    def print_document_info(documents: List[Document]):
        """
        打印文档信息（用于验证）

        Args:
            documents: Document对象列表
        """
        console = Console()

        if not documents:
            console.print("[yellow]没有文档可显示[/yellow]")
            return

        # 统计信息
        total_chars = sum(len(doc.page_content) for doc in documents)
        sources = set(doc.metadata.get('source_file', 'Unknown') for doc in documents)

        # 打印摘要
        console.print(Panel.fit(
            f"[bold cyan]文档加载摘要[/bold cyan]\n\n"
            f"文档片段数: {len(documents)}\n"
            f"总字符数: {total_chars:,}\n"
            f"来源文件数: {len(sources)}\n"
            f"文件列表: {', '.join(sources)}",
            border_style="cyan"
        ))

        # 打印前3个片段的预览
        console.print("\n[bold]前3个片段预览:[/bold]\n")

        for i, doc in enumerate(documents[:3], 1):
            preview = doc.page_content[:200].replace('\n', ' ')
            source = doc.metadata.get('source_file', 'Unknown')
            page = doc.metadata.get('page', 'N/A')

            console.print(f"[cyan]片段 {i}[/cyan] (来源: {source}, 页码: {page})")
            console.print(f"  {preview}...\n")


def demo_load_single_file():
    """
    演示：加载单个文档
    """
    console.print(Panel.fit(
        "[bold cyan]演示1：加载单个文档[/bold cyan]",
        border_style="cyan"
    ))

    loader = UniversalDocumentLoader()

    # 提示用户输入文件路径
    console.print("\n请输入文档路径（支持 .pdf / .docx / .txt）:")
    console.print("[dim]示例: C:\\Users\\test\\Desktop\\sample.pdf[/dim]")

    file_path = input("\n文件路径: ").strip()

    try:
        # 加载文档
        documents = loader.load_document(file_path)

        # 打印信息
        UniversalDocumentLoader.print_document_info(documents)

        return documents

    except Exception as e:
        console.print(f"\n[red]✗ 加载失败: {str(e)}[/red]")
        return []


def demo_create_test_file():
    """
    演示：创建测试文件（如果你没有现成的文档）
    """
    console.print(Panel.fit(
        "[bold cyan]创建测试TXT文件[/bold cyan]",
        border_style="cyan"
    ))

    test_content = """
RAG系统技术文档

第1章：什么是RAG
RAG（Retrieval-Augmented Generation）是检索增强生成技术。
它结合了信息检索和文本生成两种能力，让AI能够基于外部知识库回答问题。

第2章：RAG的核心组件
1. 文档加载器 - 解析各种格式的文档
2. 文本分块器 - 将长文档切分为小片段
3. 向量化模型 - 将文本转换为数值向量
4. 向量数据库 - 存储和检索向量
5. 生成模型 - 根据检索结果生成答案

第3章：RAG的优势
- 回答更准确，基于真实文档
- 可以引用来源，提高可信度
- 知识可以实时更新，无需重新训练模型
    """.strip()

    # 创建测试文件
    test_file = "test_document.txt"
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write(test_content)

    console.print(f"\n[green]✓ 已创建测试文件: {test_file}[/green]")

    # 加载测试文件
    loader = UniversalDocumentLoader()
    documents = loader.load_document(test_file)

    # 打印信息
    UniversalDocumentLoader.print_document_info(documents)

    return documents


if __name__ == "__main__":
    console.print("\n[bold cyan]RAG系统 - 文档加载模块测试[/bold cyan]\n")

    console.print("选择测试模式:")
    console.print("1. 加载你自己的文档")
    console.print("2. 使用系统创建的测试文档")

    choice = input("\n请输入选项 (1/2): ").strip()

    if choice == "1":
        demo_load_single_file()
    else:
        demo_create_test_file()
