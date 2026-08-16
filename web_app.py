"""
RAG系统 - Web界面。

使用 Gradio 提供文档上传、索引和问答入口。
"""

from contextvars import copy_context
from pathlib import Path
from time import perf_counter
from typing import List, Optional, Tuple

import gradio as gr

from app.config import settings
from app.core.document_chunker import DocumentChunker
from app.core.document_loader import UniversalDocumentLoader
from app.core.embedding_client import UniversalEmbeddingClient
from app.core.generator import GenerationConfig, RAGGenerator, UniversalLLMClient
from app.core.retriever import Retriever
from app.core.vector_store import VectorStore
from app.lifecycle.registry import DocumentRegistry
from app.lifecycle.service import DocumentLifecycleService
from app.observability.context import request_context
from app.observability.logging import get_logger, setup_logger
from app.observability.metrics import (
    configure_metrics,
    get_metrics,
    start_metrics_server,
)
from app.observability.tracing import (
    configure_tracing,
    mark_span_error,
    trace_span,
)

logger = get_logger(__name__)
configure_metrics(settings.metrics_enabled)
configure_tracing(
    settings.tracing_enabled,
    service_name=settings.service_name,
    environment=settings.app_env,
    endpoint=settings.otel_exporter_otlp_endpoint,
)


class RAGWebApp:
    """封装 RAG 组件并提供 Gradio 回调。"""

    def __init__(self):
        logger.info("正在初始化RAG系统...")
        self.embedding_provider = settings.default_embedding_provider
        self.llm_provider = settings.default_llm_provider
        self.initialized = False
        self.vector_store = None
        self.lifecycle_service = None

        try:
            self.embedding_client = UniversalEmbeddingClient(self.embedding_provider)
            self.vector_store = VectorStore(
                collection_name=settings.collection_name,
                uri=settings.milvus_uri,
                token=settings.milvus_token,
                db_name=settings.milvus_db_name,
            )
            self.retriever = Retriever(self.vector_store, self.embedding_client)
            self.llm_client = UniversalLLMClient(provider=self.llm_provider)
            self.rag_generator = RAGGenerator(self.llm_client)
            self.doc_loader = UniversalDocumentLoader()
            self.chunker = DocumentChunker(
                chunk_size=settings.chunk_size,
                chunk_overlap=settings.chunk_overlap,
            )
            self.registry = DocumentRegistry(settings.document_registry_path)
            self.lifecycle_service = DocumentLifecycleService(
                loader=self.doc_loader,
                chunker=self.chunker,
                embedding_client=self.embedding_client,
                vector_store=self.vector_store,
                registry=self.registry,
                upload_dir=settings.upload_dir,
                tenant_id=settings.default_tenant_id,
                collection_id=settings.collection_name,
            )
            self.initialized = True
            logger.info("RAG系统初始化完成")
        except Exception:
            logger.exception("RAG系统初始化失败")
            self.close()

    def close(self) -> None:
        """Release the Milvus connection owned by this application instance."""
        service = getattr(self, "lifecycle_service", None)
        vector_store = getattr(self, "vector_store", None)
        self.lifecycle_service = None
        self.vector_store = None
        if service is not None:
            close_service = getattr(service, "close", None)
            if callable(close_service):
                close_service()
            return
        close_store = getattr(vector_store, "close", None)
        if callable(close_store):
            close_store()

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

    @staticmethod
    def _persist_upload(file_path: Path, upload_dir: str) -> Path:
        """将上传源文件持久化到运行数据目录，避免依赖 Web 框架临时文件。"""
        return DocumentLifecycleService.persist_source_file(file_path, upload_dir)

    def _get_lifecycle_service(self) -> DocumentLifecycleService:
        service = getattr(self, "lifecycle_service", None)
        if service is not None:
            return service
        registry = getattr(self, "registry", None)
        if registry is None:
            registry = DocumentRegistry(settings.document_registry_path)
            self.registry = registry
        service = DocumentLifecycleService(
            loader=self.doc_loader,
            chunker=self.chunker,
            embedding_client=self.embedding_client,
            vector_store=self.vector_store,
            registry=registry,
            upload_dir=settings.upload_dir,
            tenant_id=settings.default_tenant_id,
            collection_id=settings.collection_name,
        )
        self.lifecycle_service = service
        return service

    def _run_lifecycle_ingest(self, file_path: Path, file_size: int) -> str:
        metrics = get_metrics()
        started = perf_counter()
        extension = file_path.suffix.lower()
        metrics.record_document_upload("accepted")
        logger.info(
            "收到文档上传请求",
            event="document_upload_received",
            operation="rag.document.ingest",
            status="started",
            file_extension=extension,
            file_size_bytes=file_size,
        )
        result = self._get_lifecycle_service().ingest(
            file_path,
            display_name=file_path.name,
        )
        elapsed = perf_counter() - started
        is_noop = result.status == "noop"
        metrics.record_document_ingestion(
            "noop" if is_noop else "success",
            elapsed,
            chunks_created=0 if is_noop else result.chunk_count,
            chunks_indexed=0 if is_noop else result.chunk_count,
        )
        status_line = "已存在，未重复构建" if is_noop else "已建立新版本"
        cleanup_line = "旧索引待清理" if result.cleanup_pending else "旧索引已处理"
        return (
            "✅ 文档处理完成！\n\n"
            f"📄 文件名: {file_path.name}\n"
            f"📊 Chunk 数: {result.chunk_count}\n"
            f"🧭 版本状态: {status_line}\n"
            f"🧹 清理状态: {cleanup_line}\n"
            f"💾 集合文档块总数: {result.collection_count}"
        )

    def upload_and_index_document(self, file) -> str:
        """校验、加载、分块、向量化并幂等写入文档。"""
        if not self.initialized:
            return "❌ 系统未正确初始化，请查看服务日志"
        if file is None:
            return "⚠️ 请先上传文件"

        with request_context(), trace_span("rag.document.ingest") as root_span:
            metrics = get_metrics()
            total_started = perf_counter()
            active_operation = "rag.document.ingest"
            active_started = total_started
            chunks = []
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

                return self._run_lifecycle_ingest(file_path, file_size)
            except Exception as exc:
                mark_span_error(root_span, exc)
                elapsed = perf_counter() - total_started
                metrics.record_component_error(active_operation, type(exc).__name__)
                if active_operation == "embedding.batch":
                    metrics.observe_embedding(
                        getattr(
                            self,
                            "embedding_provider",
                            settings.default_embedding_provider,
                        ),
                        active_operation,
                        "error",
                        perf_counter() - active_started,
                    )
                metrics.record_document_ingestion(
                    "error",
                    elapsed,
                    chunks_created=len(chunks),
                )
                logger.exception(
                    "文档处理失败",
                    event="document_indexing_completed",
                    operation="rag.document.ingest",
                    duration_ms=elapsed * 1000,
                    status="error",
                    error_type=type(exc).__name__,
                    failed_operation=active_operation,
                )
                return "❌ 文档处理失败，请查看服务日志后重试"

    def answer_question(
        self,
        message: str,
        history: Optional[List[dict]],
    ):
        """在固定执行上下文中驱动流式问答，避免跨线程恢复时丢失请求标识。"""
        stream = self._answer_question_stream(message, history)
        stream_context = copy_context()
        try:
            while True:
                try:
                    output = stream_context.run(next, stream)
                except StopIteration:
                    return
                yield output
        finally:
            stream_context.run(stream.close)

    def _answer_question_stream(
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

        with (
            request_context(),
            trace_span(
                "rag.query",
                attributes={"query.length": len(normalized_message)},
            ) as root_span,
        ):
            metrics = get_metrics()
            total_started = perf_counter()
            llm_provider = getattr(self, "llm_provider", settings.default_llm_provider)
            active_operation = "rag.retrieve"
            generation_started: float | None = None
            first_token_received = False
            logger.info(
                "收到问答请求",
                event="query_received",
                operation="rag.query",
                status="started",
                query_length=len(normalized_message),
                history_message_count=max(len(history) - 1, 0),
            )

            assistant_index: Optional[int] = None
            answer_parts: List[str] = []
            sources = ""
            try:
                retrieval_kwargs = {
                    "top_k": settings.retrieval_top_k,
                    "score_threshold": settings.retrieval_score_threshold,
                }
                lifecycle_service = getattr(self, "lifecycle_service", None)
                if lifecycle_service is not None:
                    retrieval_kwargs["result_predicate"] = (
                        lifecycle_service.active_metadata_predicate()
                    )
                retrieval_results = self.retriever.retrieve_semantic(
                    normalized_message,
                    **retrieval_kwargs,
                )
                if not retrieval_results:
                    history.append(
                        {
                            "role": "assistant",
                            "content": "⚠️ 未找到达到相关性阈值的文档内容，请先上传文档或换一种问法。",
                        }
                    )
                    elapsed = perf_counter() - total_started
                    metrics.record_no_context(llm_provider)
                    metrics.record_query(llm_provider, "no_context", elapsed)
                    logger.info(
                        "问答请求无可用上下文",
                        event="response_sent",
                        operation="rag.query",
                        duration_ms=elapsed * 1000,
                        status="no_context",
                        result_count=0,
                    )
                    yield "", history, ""
                    return

                active_operation = "rag.context.build"
                stage_started = perf_counter()
                with trace_span(
                    "rag.context.build",
                    attributes={"result.count": len(retrieval_results)},
                ):
                    sources = self._format_sources(retrieval_results)
                    context_chars = sum(
                        len(result.content) for result in retrieval_results
                    )
                logger.info(
                    "RAG 上下文构建完成",
                    event="context_built",
                    operation=active_operation,
                    duration_ms=(perf_counter() - stage_started) * 1000,
                    status="success",
                    result_count=len(retrieval_results),
                    context_chars=context_chars,
                )

                history.append({"role": "assistant", "content": ""})
                assistant_index = len(history) - 1
                active_operation = "llm.generate"
                generation_started = perf_counter()
                logger.info(
                    "开始调用 LLM 生成回答",
                    event="generation_started",
                    operation=active_operation,
                    status="started",
                    provider=llm_provider,
                )
                history[assistant_index] = {
                    "role": "assistant",
                    "content": "⏳ 正在生成回答...",
                }
                yield "", list(history), sources

                with trace_span(
                    "llm.generate",
                    attributes={"provider": llm_provider},
                ):
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
                        if not first_token_received:
                            first_token_received = True
                            first_token_duration = perf_counter() - generation_started
                            metrics.observe_first_token(
                                llm_provider, "success", first_token_duration
                            )
                            logger.info(
                                "收到 LLM 首个文本块",
                                event="first_token_received",
                                operation=active_operation,
                                duration_ms=first_token_duration * 1000,
                                status="success",
                                provider=llm_provider,
                            )
                        answer_parts.append(chunk)
                        history[assistant_index] = {
                            "role": "assistant",
                            "content": "".join(answer_parts),
                        }
                        yield "", list(history), sources

                    if not answer_parts:
                        raise RuntimeError("LLM 流式接口未返回任何文本")

                    answer_text = "".join(answer_parts)
                    history[assistant_index] = {
                        "role": "assistant",
                        "content": answer_text,
                    }
                    generation_duration = perf_counter() - generation_started
                    metrics.observe_llm_total(
                        llm_provider, "success", generation_duration
                    )
                    logger.info(
                        "LLM 回答生成完成",
                        event="generation_completed",
                        operation=active_operation,
                        duration_ms=generation_duration * 1000,
                        status="success",
                        provider=llm_provider,
                        response_chars=len(answer_text),
                    )

                elapsed = perf_counter() - total_started
                metrics.record_query(llm_provider, "success", elapsed)
                logger.info(
                    "问答响应发送完成",
                    event="response_sent",
                    operation="rag.query",
                    duration_ms=elapsed * 1000,
                    status="success",
                    result_count=len(retrieval_results),
                    response_chars=len(answer_text),
                )
                yield "", history, sources
            except Exception as exc:
                mark_span_error(root_span, exc)
                elapsed = perf_counter() - total_started
                error_type = type(exc).__name__
                metrics.record_component_error(active_operation, error_type)
                generation_duration: float | None = None
                if generation_started is not None:
                    generation_duration = perf_counter() - generation_started
                    if not first_token_received:
                        metrics.observe_first_token(
                            llm_provider, "error", generation_duration
                        )
                    metrics.observe_llm_total(
                        llm_provider, "error", generation_duration
                    )
                    logger.warning(
                        "LLM 流式生成未正常完成",
                        event="generation_completed",
                        operation="llm.generate",
                        duration_ms=generation_duration * 1000,
                        status="error",
                        error_type=error_type,
                        provider=llm_provider,
                        partial_response_chars=len("".join(answer_parts)),
                    )
                metrics.record_query(llm_provider, "error", elapsed)
                logger.exception(
                    "问答流程执行失败",
                    event="response_sent",
                    operation="rag.query",
                    duration_ms=elapsed * 1000,
                    status="error",
                    error_type=error_type,
                    failed_operation=active_operation,
                    partial_response=bool(answer_parts),
                    response_chars=len("".join(answer_parts)),
                )

                if assistant_index is not None and answer_parts:
                    partial_answer = "".join(answer_parts)
                    interruption_notice = (
                        "\n\n> ⚠️ 模型连接在流式生成过程中中断，"
                        "以上为已收到的部分回答，请稍后重试。"
                    )
                    history[assistant_index] = {
                        "role": "assistant",
                        "content": partial_answer + interruption_notice,
                    }
                    yield "", list(history), sources
                    return

                public_error = "❌ 系统暂时无法完成回答，请稍后重试并查看服务日志"
                assistant_message = {"role": "assistant", "content": public_error}
                if assistant_index is not None:
                    history[assistant_index] = assistant_message
                else:
                    history.append(assistant_message)
                yield "", list(history), ""

    def _format_sources(self, retrieval_results) -> str:
        """将来源、页码、检索距离和重排分数格式化为 Markdown。"""
        if not retrieval_results:
            return "未找到相关来源"

        sections = ["### 📚 引用来源", ""]
        for index, result in enumerate(retrieval_results, 1):
            source = result.source or "未知来源"
            page = f" 第{result.page_number}页" if result.page_number else ""
            metrics = []
            if result.distance is not None:
                metrics.append(f"距离: {result.distance:.4f}")
            if result.lexical_score is not None:
                metrics.append(f"BM25: {result.lexical_score:.4f}")
            if result.fusion_score is not None:
                metrics.append(f"RRF: {result.fusion_score:.6f}")
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
        gr.Markdown("""
            # 🤖 RAG知识库问答系统

            上传文档后，可以向 AI 提问文档相关问题。系统会检索相关内容并生成答案。

            **支持格式**: PDF、Word (.docx)、TXT
            """)

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

        gr.Markdown(f"""
            ---

            💡 **使用提示**:
            - 上传文档后等待索引完成
            - 提问时尽量具体明确
            - 当前对话历史仅用于页面展示，尚未参与上下文检索
            - 查看右侧“引用来源”了解答案依据

            ⚙️ **当前配置**:
            - Embedding: {rag_app.embedding_provider}
            - LLM: {rag_app.llm_provider}
            """)

        upload_btn.click(
            fn=rag_app.upload_and_index_document,
            inputs=[file_upload],
            outputs=[upload_status],
        )
        submit_btn.click(
            fn=rag_app.answer_question,
            inputs=[msg, chatbot],
            outputs=[msg, chatbot, sources_display],
            stream_every=0.05,
        )
        msg.submit(
            fn=rag_app.answer_question,
            inputs=[msg, chatbot],
            outputs=[msg, chatbot, sources_display],
            stream_every=0.05,
        )
        clear_btn.click(
            fn=rag_app.clear_conversation,
            outputs=[chatbot, sources_display],
        )

    demo.unload(rag_app.close)

    return demo, custom_css


if __name__ == "__main__":
    setup_logger(
        log_level=settings.log_level,
        log_file_path=settings.log_file_path,
        rotation=settings.log_rotation,
        retention=settings.log_retention,
        service=settings.service_name,
        environment=settings.app_env,
        console_format=settings.log_console_format,
        file_format=settings.log_file_format,
    )
    start_metrics_server(
        host=settings.metrics_host,
        port=settings.metrics_port,
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
