"""
RAG系统 - Web界面
使用Gradio搭建对话式问答界面
"""

import os
import gradio as gr
from typing import List, Tuple
from dotenv import load_dotenv
from rich.console import Console

# 导入前面课程的模块
from document_loader import UniversalDocumentLoader
from document_chunker import DocumentChunker
from embedding_client import UniversalEmbeddingClient
from vector_store import VectorStore
from retriever import Retriever
from generator import RAGGenerator, UniversalLLMClient, GenerationConfig

# 加载环境变量
load_dotenv()
console = Console()


class RAGWebApp:
    """
    RAG Web应用
    封装所有组件，提供统一接口
    """

    def __init__(self):
        """初始化RAG系统"""
        console.print("[cyan]正在初始化RAG系统...[/cyan]")

        # 获取配置
        self.embedding_provider = os.getenv('DEFAULT_EMBEDDING_PROVIDER', 'openai')
        self.llm_provider = os.getenv('DEFAULT_LLM_PROVIDER', 'openai')

        # 初始化组件
        try:
            # Embedding客户端
            self.embedding_client = UniversalEmbeddingClient(self.embedding_provider)

            # 向量存储
            self.vector_store = VectorStore(
                collection_name="rag_web_app",
                persist_directory="./rag_web_chroma_db"
            )

            # 检索器
            self.retriever = Retriever(self.vector_store, self.embedding_client)

            # LLM客户端
            self.llm_client = UniversalLLMClient(provider=self.llm_provider)

            # RAG生成器
            self.rag_generator = RAGGenerator(self.llm_client)

            # 文档加载和分块器
            self.doc_loader = UniversalDocumentLoader()
            self.chunker = DocumentChunker(chunk_size=500, chunk_overlap=100)

            console.print("[green]✓ RAG系统初始化完成[/green]")
            self.initialized = True

        except Exception as e:
            console.print(f"[red]✗ 初始化失败: {str(e)}[/red]")
            self.initialized = False

    def upload_and_index_document(self, file) -> str:
        """
        上传并索引文档

        Args:
            file: Gradio上传的文件对象

        Returns:
            处理结果消息
        """
        if not self.initialized:
            return "❌ 系统未正确初始化，请检查API配置"

        if file is None:
            return "⚠️ 请先上传文件"

        try:
            file_path = file.name
            console.print(f"[cyan]处理文件: {file_path}[/cyan]")

            # 1. 加载文档
            documents = self.doc_loader.load_document(file_path)

            # 2. 分块
            chunks = self.chunker.chunk_documents_recursive(documents)

            # 3. 向量化
            texts = [chunk.page_content for chunk in chunks]
            embeddings = self.embedding_client.embed_texts_batch(
                texts,
                show_progress=False
            )

            # 4. 存储
            self.vector_store.add_documents(chunks, embeddings)

            result_msg = (
                f"✅ 文档处理完成！\n\n"
                f"📄 文件名: {os.path.basename(file_path)}\n"
                f"📊 分块数: {len(chunks)}\n"
                f"💾 已索引: {self.vector_store.collection.count()} 个文档块\n\n"
                f"现在你可以开始提问了！"
            )

            console.print("[green]✓ 文档索引完成[/green]")
            return result_msg

        except Exception as e:
            error_msg = f"❌ 文档处理失败: {str(e)}"
            console.print(f"[red]{error_msg}[/red]")
            return error_msg

    def answer_question(
        self,
        message: str,
        history: List[dict]
    ):
        """
        回答用户问题

        Args:
            message: 用户问题
            history: 对话历史（Gradio messages 格式，元素为
                     {"role": "user"/"assistant", "content": str}）

        Yields:
            (清空的输入框, 更新的对话历史, 来源信息)
        """
        history = list(history or [])

        if not self.initialized:
            history.append({"role": "user", "content": message})
            history.append({
                "role": "assistant",
                "content": "❌ 系统未正确初始化，请检查API配置"
            })
            yield "", history, ""
            return

        if not message.strip():
            yield "", history, ""
            return

        try:
            # 1. 检索相关文档
            retrieval_results = self.retriever.retrieve_semantic(
                message,
                top_k=3
            )

            if not retrieval_results:
                answer = "⚠️ 未找到相关文档，请先上传文档或检查知识库。"
                history.append({"role": "user", "content": message})
                history.append({"role": "assistant", "content": answer})
                yield "", history, ""
                return

            # 2. 生成答案（流式）
            answer_parts = []

            # 先添加用户问题，再追加一条空的助手消息用于流式填充
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": ""})

            # 流式生成答案
            for chunk in self.rag_generator.generate_answer_stream(
                message,
                retrieval_results,
                config=GenerationConfig(temperature=0.3)
            ):
                answer_parts.append(chunk)
                # 更新对话历史中的答案
                history[-1] = {
                    "role": "assistant",
                    "content": ''.join(answer_parts)
                }
                yield "", history, self._format_sources(retrieval_results)

            # 3. 格式化来源信息
            sources = self._format_sources(retrieval_results)

            yield "", history, sources

        except Exception as e:
            error_msg = f"❌ 生成答案时出错: {str(e)}"
            console.print(f"[red]{error_msg}[/red]")
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": error_msg})
            yield "", history, ""

    def _format_sources(self, retrieval_results) -> str:
        """
        格式化来源信息

        Args:
            retrieval_results: 检索结果列表

        Returns:
            Markdown格式的来源信息
        """
        if not retrieval_results:
            return "未找到相关来源"

        sources_md = "### 📚 引用来源\n\n"

        for i, result in enumerate(retrieval_results, 1):
            source = result.source or "未知来源"
            page = f"第{result.page}页" if result.page else ""
            score = f"{result.score:.4f}"

            # 截取内容预览
            content_preview = result.content[:150].replace('\n', ' ')
            if len(result.content) > 150:
                content_preview += "..."

            sources_md += (
                f"**[{i}] {source}** {page} (相似度: {score})\n\n"
                f"> {content_preview}\n\n"
                f"---\n\n"
            )

        return sources_md

    def clear_conversation(self) -> Tuple[List, str]:
        """
        清空对话历史

        Returns:
            (空的对话历史, 空的来源信息)
        """
        return [], ""


def create_web_interface():
    """
    创建Gradio Web界面
    """
    # 初始化RAG系统
    rag_app = RAGWebApp()

    # 自定义CSS样式
    custom_css = """
    .gradio-container {
        max-width: 1200px !important;
    }
    #chatbot {
        height: 500px !important;
    }
    """

    # 创建界面
    # 注意: Gradio 6 起 theme / css 需要传给 launch()，不再放在 Blocks 构造函数里
    with gr.Blocks(title="RAG知识库问答系统") as demo:

        # 标题和说明
        gr.Markdown(
            """
            # 🤖 RAG知识库问答系统

            上传文档后，就可以向AI提问文档相关问题。系统会从文档中检索相关内容并生成准确答案。

            **支持格式**: PDF、Word (.docx)、TXT
            """
        )

        with gr.Row():
            # 左侧：对话区域
            with gr.Column(scale=2):
                chatbot = gr.Chatbot(
                    label="对话历史",
                    height=500,
                    elem_id="chatbot",
                    render_markdown=True
                )

                with gr.Row():
                    msg = gr.Textbox(
                        label="输入问题",
                        placeholder="请输入你的问题...",
                        scale=4,
                        lines=2
                    )
                    submit_btn = gr.Button("发送", variant="primary", scale=1)

                with gr.Row():
                    clear_btn = gr.Button("🗑️ 清空对话")

            # 右侧：文档上传和来源显示
            with gr.Column(scale=1):
                with gr.Accordion("📤 上传文档", open=True):
                    file_upload = gr.File(
                        label="选择文件",
                        file_types=[".pdf", ".docx", ".txt"]
                    )
                    upload_btn = gr.Button("📥 上传并索引", variant="secondary")
                    upload_status = gr.Textbox(
                        label="处理状态",
                        lines=8,
                        interactive=False
                    )

                with gr.Accordion("📚 引用来源", open=True):
                    sources_display = gr.Markdown(
                        value="上传文档并提问后，这里会显示答案的引用来源。"
                    )

        # 底部信息
        gr.Markdown(
            """
            ---

            💡 **使用提示**:
            - 上传文档后稍等几秒，等待索引完成
            - 提问时尽量具体明确
            - 可以连续对话，系统会记住上下文
            - 查看右侧"引用来源"了解答案依据

            ⚙️ **当前配置**:
            - Embedding: """ + rag_app.embedding_provider + """
            - LLM: """ + rag_app.llm_provider + """
            """
        )

        # 事件绑定
        # 文档上传
        upload_btn.click(
            fn=rag_app.upload_and_index_document,
            inputs=[file_upload],
            outputs=[upload_status]
        )

        # 发送消息（支持流式输出）
        submit_event = submit_btn.click(
            fn=rag_app.answer_question,
            inputs=[msg, chatbot],
            outputs=[msg, chatbot, sources_display]
        )

        # 回车发送
        msg.submit(
            fn=rag_app.answer_question,
            inputs=[msg, chatbot],
            outputs=[msg, chatbot, sources_display]
        )

        # 清空对话
        clear_btn.click(
            fn=rag_app.clear_conversation,
            outputs=[chatbot, sources_display]
        )

    return demo, custom_css


if __name__ == "__main__":
    console.print("\n[bold cyan]启动RAG Web服务...[/bold cyan]\n")

    # 创建界面
    demo, custom_css = create_web_interface()

    # 启动服务
    console.print("[green]✓ Web服务已启动[/green]")
    console.print("[yellow]访问地址: http://localhost:7860[/yellow]")
    console.print("[yellow]按 Ctrl+C 停止服务[/yellow]\n")

    demo.launch(
        server_name="0.0.0.0",  # 允许外网访问
        server_port=7860,
        share=False,  # 设为True可生成公网链接（临时）
        show_error=True,
        theme=gr.themes.Soft(),
        css=custom_css
    )
