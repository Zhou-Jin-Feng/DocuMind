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
    """根据扩展名选择加载器，并统一规范文档元数据。"""

    LOADERS = {
        ".pdf": PyPDFLoader,
        ".docx": Docx2txtLoader,
        ".txt": TextLoader,
    }

    def __init__(self):
        self.logger = get_logger(__name__)

    @staticmethod
    def _build_document_id(file_path: str) -> str:
        """基于文件名和文件内容生成稳定文档 ID。"""
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
        """补充稳定 ID、文件名和从 1 开始的 PDF 页码。"""
        file_name = Path(file_path).name
        for document in documents:
            raw_page = document.metadata.get("page")
            page_number = raw_page + 1 if file_ext == ".pdf" and isinstance(raw_page, int) else None

            # 不将 Gradio 临时文件的绝对路径写入向量库。
            document.metadata["source"] = file_name
            document.metadata["source_file"] = file_name
            document.metadata["file_type"] = file_ext
            document.metadata["document_id"] = document_id
            if page_number is not None:
                document.metadata["page_number"] = page_number

    def _load_text(self, file_path: str) -> List[Document]:
        """依次尝试常见中文文本编码。"""
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
        """加载单个文档。"""
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"文件不存在或不是普通文件: {file_path}")

        file_ext = path.suffix.lower()
        if file_ext not in self.LOADERS:
            raise ValueError(
                f"不支持的文件格式: {file_ext or '无扩展名'}；"
                f"目前支持: {', '.join(self.LOADERS.keys())}"
            )

        self.logger.info(f"正在加载文档: {path.name}")
        try:
            if file_ext == ".txt":
                documents = self._load_text(str(path))
            else:
                documents = self.LOADERS[file_ext](str(path)).load()

            if not documents:
                raise ValueError(f"文档没有可读取的内容: {path.name}")

            document_id = self._build_document_id(str(path))
            self._normalize_metadata(documents, str(path), file_ext, document_id)
            self.logger.info(f"成功加载 {len(documents)} 个文档片段: {path.name}")
            return documents
        except Exception:
            self.logger.exception(f"文档加载失败: {path.name}")
            raise

    def load_directory(self, dir_path: str) -> List[Document]:
        """按文件名排序，加载目录下所有支持的文档。"""
        directory = Path(dir_path)
        if not directory.is_dir():
            raise NotADirectoryError(f"不是有效的目录: {dir_path}")

        supported_files = sorted(
            path for path in directory.iterdir()
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
                self.logger.warning(f"跳过文件 {file_path.name}: {exc}")

        self.logger.info(f"目录加载完成，共 {len(all_documents)} 个文档片段")
        return all_documents

    def print_document_info(self, documents: List[Document]) -> None:
        """输出文档摘要，供手动验证使用。"""
        if not documents:
            self.logger.info("没有文档可显示")
            return

        total_chars = sum(len(document.page_content) for document in documents)
        sources = sorted({document.metadata.get("source_file", "Unknown") for document in documents})
        self.logger.info(
            f"文档加载摘要: 片段={len(documents)}, 字符={total_chars}, "
            f"来源={len(sources)} ({', '.join(sources)})"
        )

        for index, document in enumerate(documents[:3], 1):
            preview = document.page_content[:200].replace("\n", " ")
            source = document.metadata.get("source_file", "Unknown")
            page = document.metadata.get("page_number", "N/A")
            self.logger.info(f"片段 {index} (来源: {source}, 页码: {page}): {preview}...")

def demo_load_single_file():
    """
    演示：加载单个文档
    """
    logger.info("演示1：加载单个文档")

    loader = UniversalDocumentLoader()

    # 提示用户输入文件路径
    logger.info("\n请输入文档路径（支持 .pdf / .docx / .txt）:")
    logger.info("示例: C:\\Users\\test\\Desktop\\sample.pdf")

    file_path = input("\n文件路径: ").strip()

    try:
        # 加载文档
        documents = loader.load_document(file_path)

        # 打印信息
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

    # 创建测试文件
    test_file = "test_document.txt"
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write(test_content)

    logger.info(f"\n已创建测试文件: {test_file}")

    # 加载测试文件
    loader = UniversalDocumentLoader()
    documents = loader.load_document(test_file)

    # 打印信息
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
