"""
RAG系统 - Web界面。

使用 Gradio 提供文档上传、索引和问答入口。
"""

from pathlib import Path
from typing import List, Optional, Tuple

import gradio as gr

from app.config import settings
from app.core.document_chunker import DocumentChunker
from app.core.document_loader import UniversalDocumentLoader
from app.core.embedding_client import UniversalEmbeddingClient
from app.core.generator import GenerationConfig, RAGGenerator, UniversalLLMClient
from app.core.retriever import Retriever
from app.core.vector_store import VectorStore
from app.utils.logger import get_logger, setup_logger

logger = get_logger(__name__)


class RAGWebApp:
    """封装 RAG 组件并提供 Gradio 回调。"""

    def __init__(self):
        logger.info("正在初始化RAG系统...")
        self.embedding_provider = settings.default_embedding_provider
        self.llm_provider = settings.default_llm_provider
        self.initialized = False

        try:
            self.embedding_client = UniversalEmbeddingClient(self.embedding_provider)
            self.vector_store = VectorStore(
                collection_name=settings.collection_name,
                persist_directory=settings.chroma_persist_dir,
            )
            self.retriever = Retriever(self.vector_store, self.embedding_client)
            self.llm_client = UniversalLLMClient(provider=self.llm_provider)
            self.rag_generator = RAGGenerator(self.llm_client)
            self.doc_loader = UniversalDocumentLoader()
            self.chunker = DocumentChunker(
                chunk_size=settings.chunk_size,
                chunk_overlap=settings.chunk_overlap,
            )
            self.initialized = True
            logger.info("RAG系统初始化完成")
        except Exception:
            logger.exception("RAG系统初始化失败")

    @staticmethod
    def _resolve_upload_path(file) -> Path:
        """兼容 Gradio 文件对象和直接传入的路径。"""
        if isinstance(file, (str, Path)):
            raw_path = str(file)
        else:
            raw_path = str(getattr(file, "name", ""))
        if not raw_path.strip():
            raise ValueError("未获取到上传文件路径")
        return Path(raw_path)

    def upload_and_index_document(self, file) -> str:
        """校验、加载、分块、向量化并幂等写入文档。"""
        if not self.initialized:
            return "❌ 系统未正确初始化，请查看服务日志"
        if file is None:
            return "⚠️ 请先上传文件"

        try:
            file_path = self._resolve_upload_path(file)
            if not file_path.exists() or not file_path.is_file():
                return "❌ 上传文件不存在或不可读取"

            extension = file_path.suffix.lower()
            if extension not in settings.allowed_extensions:
                allowed = "、".join(settings.allowed_extensions)
                return f"❌ 不支持的文件格式，仅允许: {allowed}"

            max_bytes = settings.max_upload_size_mb * 1024 * 1024
            file_size = file_path.stat().st_size
            if file_size > max_bytes:
                return f"❌ 文件过大，最大允许 {settings.max_upload_size_mb} MB"

            logger.info(
                f"开始处理上传文件: name={file_path.name}, size_bytes={file_size}"
            )
            documents = self.doc_loader.load_document(str(file_path))
            if not documents:
                return "❌ 文档中没有可加载的内容"

            chunks = self.chunker.chunk_documents_recursive(documents)
            if not chunks:
                return "❌ 文档分块后没有有效内容"

            texts = [chunk.page_content for chunk in chunks]
            embeddings = self.embedding_client.embed_texts_batch(
                texts,
                show_progress=False,
            )
            if len(embeddings) != len(chunks):
                raise RuntimeError(
                    f"向量数量与分块数量不一致: {len(embeddings)} != {len(chunks)}"
                )

            self.vector_store.add_documents(chunks, embeddings)
            collection_count = self.vector_store.collection.count()
            logger.info(
                f"文档索引完成: name={file_path.name}, chunks={len(chunks)}, "
                f"collection_count={collection_count}"
            )
            return (
                "✅ 文档处理完成！\n\n"
                f"📄 文件名: {file_path.name}\n"
                f"📊 本次分块数: {len(chunks)}\n"
                f"💾 集合文档块总数: {collection_count}\n\n"
                "现在你可以开始提问了！"
            )
        except Exception:
            logger.exception("文档处理失败")
            return "❌ 文档处理失败，请查看服务日志后重试"

    def answer_question(
        self,
        message: str,
        history: Optional[List[dict]],
    ):
        """检索相关文档并流式生成回答。"""
        history = list(history or [])
        normalized_message = (message or "").strip()
        if not normalized_message:
            yield "", history, ""
            return

        history.append({"role": "user", "content": normalized_message})
        if not self.initialized:
            history.append(
                {
                    "role": "assistant",
                    "content": "❌ 系统未正确初始化，请查看服务日志",
                }
            )
            yield "", history, ""
            return

        assistant_index: Optional[int] = None
        try:
            retrieval_results = self.retriever.retrieve_semantic(
                normalized_message,
                top_k=settings.retrieval_top_k,
                score_threshold=settings.retrieval_score_threshold,
            )
            if not retrieval_results:
                history.append(
                    {
                        "role": "assistant",
                        "content": "⚠️ 未找到达到相关性阈值的文档内容，请先上传文档或换一种问法。",
                    }
                )
                yield "", history, ""
                return

            sources = self._format_sources(retrieval_results)
            history.append({"role": "assistant", "content": ""})
            assistant_index = len(history) - 1
            answer_parts: List[str] = []

            for chunk in self.rag_generator.generate_answer_stream(
                normalized_message,
                retrieval_results,
                config=GenerationConfig(
                    temperature=settings.llm_temperature,
                    max_tokens=settings.llm_max_tokens,
                    stream=True,
                ),
            ):
                if not chunk:
                    continue
                answer_parts.append(chunk)
                history[assistant_index] = {
                    "role": "assistant",
                    "content": "".join(answer_parts),
                }
                yield "", list(history), sources

            if not answer_parts:
                raise RuntimeError("LLM 流式接口未返回任何文本")
            yield "", history, sources
        except Exception:
            logger.exception("问答流程执行失败")
            public_error = "❌ 系统暂时无法完成回答，请稍后重试并查看服务日志"
            assistant_message = {"role": "assistant", "content": public_error}
            if assistant_index is not None:
                history[assistant_index] = assistant_message
            else:
                history.append(assistant_message)
            yield "", history, ""

    def _format_sources(self, retrieval_results) -> str:
        """将来源、页码、检索距离和重排分数格式化为 Markdown。"""
        if not retrieval_results:
            return "未找到相关来源"

        sections = ["### 📚 引用来源", ""]
        for index, result in enumerate(retrieval_results, 1):
            source = result.source or "未知来源"
            page = f" 第{result.page_number}页" if result.page_number else ""
            metrics = [f"距离: {result.distance:.4f}"]
            if result.rerank_score is not None:
                metrics.append(f"重排分数: {result.rerank_score:.4f}")
            content_preview = result.content[:150].replace("\n", " ")
            if len(result.content) > 150:
                content_preview += "..."
            sections.extend(
                [
                    f"**[{index}] {source}**{page} ({', '.join(metrics)})",
                    "",
                    f"> {content_preview}",
                    "",
                    "---",
                    "",
                ]
            )
        return "\n".join(sections)

    def clear_conversation(self) -> Tuple[List, str]:
        return [], ""


def create_web_interface():
    """创建 Gradio Web 界面。"""
    rag_app = RAGWebApp()
    custom_css = """
    .gradio-container {
        max-width: 1200px !important;
    }
    #chatbot {
        height: 500px !important;
    }
    """

    with gr.Blocks(title="RAG知识库问答系统") as demo:
        gr.Markdown(
            """
            # 🤖 RAG知识库问答系统

            上传文档后，可以向 AI 提问文档相关问题。系统会检索相关内容并生成答案。

            **支持格式**: PDF、Word (.docx)、TXT
            """
        )

        with gr.Row():
            with gr.Column(scale=2):
                chatbot = gr.Chatbot(
                    label="对话历史",
                    height=500,
                    elem_id="chatbot",
                    render_markdown=True,
                )
                with gr.Row():
                    msg = gr.Textbox(
                        label="输入问题",
                        placeholder="请输入你的问题...",
                        scale=4,
                        lines=2,
                    )
                    submit_btn = gr.Button("发送", variant="primary", scale=1)
                clear_btn = gr.Button("🗑️ 清空对话")

            with gr.Column(scale=1):
                with gr.Accordion("📤 上传文档", open=True):
                    file_upload = gr.File(
                        label="选择文件",
                        file_types=settings.allowed_extensions,
                    )
                    upload_btn = gr.Button("📥 上传并索引", variant="secondary")
                    upload_status = gr.Textbox(
                        label="处理状态",
                        lines=8,
                        interactive=False,
                    )
                with gr.Accordion("📚 引用来源", open=True):
                    sources_display = gr.Markdown(
                        value="上传文档并提问后，这里会显示答案的引用来源。"
                    )

        gr.Markdown(
            f"""
            ---

            💡 **使用提示**:
            - 上传文档后等待索引完成
            - 提问时尽量具体明确
            - 当前对话历史仅用于页面展示，尚未参与上下文检索
            - 查看右侧“引用来源”了解答案依据

            ⚙️ **当前配置**:
            - Embedding: {rag_app.embedding_provider}
            - LLM: {rag_app.llm_provider}
            """
        )

        upload_btn.click(
            fn=rag_app.upload_and_index_document,
            inputs=[file_upload],
            outputs=[upload_status],
        )
        submit_btn.click(
            fn=rag_app.answer_question,
            inputs=[msg, chatbot],
            outputs=[msg, chatbot, sources_display],
        )
        msg.submit(
            fn=rag_app.answer_question,
            inputs=[msg, chatbot],
            outputs=[msg, chatbot, sources_display],
        )
        clear_btn.click(
            fn=rag_app.clear_conversation,
            outputs=[chatbot, sources_display],
        )

    return demo, custom_css


if __name__ == "__main__":
    setup_logger(
        log_level=settings.log_level,
        log_file_path=settings.log_file_path,
        rotation=settings.log_rotation,
        retention=settings.log_retention,
    )
    logger.info("启动RAG Web服务...")
    demo, custom_css = create_web_interface()
    logger.info(f"访问地址: http://localhost:{settings.server_port}")
    logger.info("按 Ctrl+C 停止服务")
    demo.launch(
        server_name=settings.server_host,
        server_port=settings.server_port,
        share=settings.share_gradio,
        show_error=False,
        theme=gr.themes.Soft(),
        css=custom_css,
    )
