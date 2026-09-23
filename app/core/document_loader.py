"""
RAG 系统文档加载模块。

支持 PDF、DOCX、TXT，并统一补充可追踪的文档元数据。
"""

import hashlib
from pathlib import Path
from typing import List

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_core.documents import Document

from app.utils.logger import get_logger

logger = get_logger(__name__)


class UniversalDocumentLoader:
    """
    统一文档加载器。

    根据文件扩展名选择 LangChain Loader，并把不同格式返回的
    ``Document`` 元数据整理成项目统一的结构。这样后续分块、索引和
    引用来源时，不需要关心原始文件格式的差异。
    """

    # 扩展名到 LangChain 加载器的映射；TXT 单独处理以兼容常见中文编码。
    LOADERS = {
        ".pdf": PyPDFLoader,
        ".docx": Docx2txtLoader,
        ".txt": TextLoader,
    }

    def __init__(self):
        self.logger = get_logger(__name__)

    @staticmethod
    def _build_document_id(file_path: str) -> str:
        """
        根据文件名和文件内容生成稳定文档 ID。

        文件名参与哈希是为了区分同内容但来源不同的文件；内容按块读取，
        避免一次性将大文件全部载入内存。返回值会写入每个页面/文档片段的
        ``document_id`` 元数据。
        """
        path = Path(file_path)
        digest = hashlib.sha256()
        digest.update(path.name.lower().encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as file_obj:
            for block in iter(lambda: file_obj.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _normalize_metadata(
        documents: List[Document], file_path: str, file_ext: str, document_id: str
    ) -> None:
        """
        统一补充可追踪元数据。

        PDF Loader 的 ``page`` 通常从 0 开始，因此这里转换成用户可读的
        ``page_number``（从 1 开始）。同时只保存文件名，不把本机绝对路径
        写进向量库，避免暴露运行环境路径。
        """
        file_name = Path(file_path).name
        for document in documents:
            raw_page = document.metadata.get("page")
            page_number = (
                raw_page + 1
                if file_ext == ".pdf" and isinstance(raw_page, int)
                else None
            )

            # 不将 上传临时文件的绝对路径写入向量库。
            document.metadata["source"] = file_name
            document.metadata["source_file"] = file_name
            document.metadata["file_type"] = file_ext
            document.metadata["document_id"] = document_id
            if page_number is not None:
                document.metadata["page_number"] = page_number

    def _load_text(self, file_path: str) -> List[Document]:
        """
        加载纯文本文件。

        先尝试带 BOM 的 UTF-8，再尝试兼容中文 Windows 文件的 GB18030；
        两种编码都失败时重新抛出最后一次解码异常。
        """
        last_error: UnicodeDecodeError | None = None
        path = Path(file_path)
        for encoding in ("utf-8-sig", "gb18030"):
            try:
                content = path.read_text(encoding=encoding)
                return [Document(page_content=content, metadata={"source": str(path)})]
            except UnicodeDecodeError as exc:
                last_error = exc
                self.logger.warning(f"使用 {encoding} 解码失败，尝试下一种编码")
        if last_error is not None:
            raise last_error
        return []

    def load_document(self, file_path: str) -> List[Document]:
        """
        加载单个 PDF、DOCX 或 TXT 文档。

        返回的每个 ``Document`` 都已经经过元数据规范化，可直接交给
        ``DocumentChunker`` 继续处理。文件不存在、格式不支持或文档为空时
        会抛出明确异常，并记录结构化失败日志。
        """
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"文件不存在或不是普通文件: {file_path}")

        file_ext = path.suffix.lower()
        if file_ext not in self.LOADERS:
            raise ValueError(
                f"不支持的文件格式: {file_ext or '无扩展名'}；"
                f"目前支持: {', '.join(self.LOADERS.keys())}"
            )

        self.logger.info(
            "正在加载文档",
            file_extension=file_ext,
        )
        try:
            if file_ext == ".txt":
                documents = self._load_text(str(path))
            else:
                documents = self.LOADERS[file_ext](str(path)).load()

            if not documents:
                raise ValueError(f"文档没有可读取的内容: {path.name}")

            document_id = self._build_document_id(str(path))
            self._normalize_metadata(documents, str(path), file_ext, document_id)
            self.logger.info(
                "文档加载完成",
                file_extension=file_ext,
                document_count=len(documents),
                document_ref=document_id[:12],
            )
            return documents
        except Exception as exc:
            self.logger.error(
                "文档加载失败",
                file_extension=file_ext,
                error_type=type(exc).__name__,
            )
            raise

    def load_directory(self, dir_path: str) -> List[Document]:
        """
        按文件名排序加载目录中的所有支持文件。

        单个文件加载失败不会阻止其他文件继续处理；失败文件会记录警告，
        方法最终返回成功加载的片段集合。
        """
        directory = Path(dir_path)
        if not directory.is_dir():
            raise NotADirectoryError(f"不是有效的目录: {dir_path}")

        supported_files = sorted(
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in self.LOADERS
        )
        if not supported_files:
            self.logger.warning("目录中没有找到支持的文档")
            return []

        all_documents: List[Document] = []
        for file_path in supported_files:
            try:
                all_documents.extend(self.load_document(str(file_path)))
            except Exception as exc:
                self.logger.warning(
                    "跳过一个加载失败的文件",
                    file_extension=file_path.suffix.lower(),
                    error_type=type(exc).__name__,
                )

        self.logger.info(f"目录加载完成，共 {len(all_documents)} 个文档片段")
        return all_documents

    def print_document_info(self, documents: List[Document]) -> None:
        """输出加载摘要和最多三个片段预览，供手动检查解析结果。"""
        if not documents:
            self.logger.info("没有文档可显示")
            return

        total_chars = sum(len(document.page_content) for document in documents)
        sources = sorted(
            {document.metadata.get("source_file", "Unknown") for document in documents}
        )
        self.logger.info(
            f"文档加载摘要: 片段={len(documents)}, 字符={total_chars}, "
            f"来源={len(sources)} ({', '.join(sources)})"
        )

        for index, document in enumerate(documents[:3], 1):
            preview = document.page_content[:200].replace("\n", " ")
            source = document.metadata.get("source_file", "Unknown")
            page = document.metadata.get("page_number", "N/A")
            self.logger.info(
                f"片段 {index} (来源: {source}, 页码: {page}): {preview}..."
            )


def demo_load_single_file():
    """
    演示：加载单个文档
    """
    logger.info("演示1：加载单个文档")

    loader = UniversalDocumentLoader()

    logger.info("\n请输入文档路径（支持 .pdf / .docx / .txt）:")
    logger.info("示例: ./documents/sample.pdf")

    file_path = input("\n文件路径: ").strip()

    try:
        documents = loader.load_document(file_path)
        loader.print_document_info(documents)

        return documents

    except Exception as e:
        logger.error(f"\n加载失败: {str(e)}")
        return []


def demo_create_test_file():
    """
    演示：创建测试文件（如果你没有现成的文档）
    """
    logger.info("创建测试TXT文件")

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

    test_file = "test_document.txt"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(test_content)

    logger.info(f"\n已创建测试文件: {test_file}")

    loader = UniversalDocumentLoader()
    documents = loader.load_document(test_file)
    loader.print_document_info(documents)

    return documents


if __name__ == "__main__":
    logger.info("\nRAG系统 - 文档加载模块测试\n")

    logger.info("选择测试模式:")
    logger.info("1. 加载你自己的文档")
    logger.info("2. 使用系统创建的测试文档")

    choice = input("\n请输入选项 (1/2): ").strip()

    if choice == "1":
        demo_load_single_file()
    else:
        demo_create_test_file()
