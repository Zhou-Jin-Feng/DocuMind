"""Framework-neutral orchestration for streaming RAG answers."""

from __future__ import annotations

from contextvars import copy_context
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any, Callable, Iterator, Literal

from app.config import Settings
from app.core.generator import GenerationConfig
from app.observability.context import request_context
from app.observability.logging import get_logger
from app.observability.metrics import get_metrics
from app.observability.tracing import mark_span_error, trace_span

logger = get_logger(__name__)

ChatEventType = Literal["status", "sources", "token", "done", "error"]


@dataclass(frozen=True, slots=True)
class SourceReference:
    """Public, provider-neutral citation returned to UI clients."""

    rank: int
    source: str
    page_number: int | None
    excerpt: str
    distance: float | None = None
    lexical_score: float | None = None
    fusion_score: float | None = None
    rerank_score: float | None = None
    chunk_id: str | None = None

    @classmethod
    def from_result(cls, result: Any) -> "SourceReference":
        metadata = getattr(result, "metadata", {}) or {}
        content = str(getattr(result, "content", ""))
        excerpt = " ".join(content.split())
        if len(excerpt) > 240:
            excerpt = f"{excerpt[:237]}..."
        return cls(
            rank=int(getattr(result, "rank", 0) or 0),
            source=str(getattr(result, "source", "") or "未知来源"),
            page_number=getattr(result, "page_number", None),
            excerpt=excerpt,
            distance=getattr(result, "distance", None),
            lexical_score=getattr(result, "lexical_score", None),
            fusion_score=getattr(result, "fusion_score", None),
            rerank_score=getattr(result, "rerank_score", None),
            chunk_id=str(metadata.get("chunk_id")) if metadata.get("chunk_id") else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ChatEvent:
    """One event in the transport-independent answer stream."""

    type: ChatEventType
    data: dict[str, Any]


class RAGService:
    """Run retrieval and generation without depending on a Web framework."""

    NO_CONTEXT_MESSAGE = "未找到达到相关性阈值的文档内容，请先上传文档或换一种问法。"
    PUBLIC_ERROR_MESSAGE = "系统暂时无法完成回答，请稍后重试。"
    INTERRUPTION_MESSAGE = "模型连接在流式生成过程中中断，已保留收到的部分回答。"

    def __init__(
        self,
        *,
        retriever: Any,
        rag_generator: Any,
        settings: Settings,
        lifecycle_service: Any | None = None,
        metrics_getter: Callable[[], Any] = get_metrics,
    ) -> None:
        self.retriever = retriever
        self.rag_generator = rag_generator
        self.settings = settings
        self.lifecycle_service = lifecycle_service
        self.metrics_getter = metrics_getter

    def stream_answer(
        self,
        question: str,
        *,
        request_id: str | None = None,
    ) -> Iterator[ChatEvent]:
        """Keep one ContextVar context across thread-pooled iterator resumes."""

        stream = self._stream_answer(question, request_id=request_id)
        stream_context = copy_context()
        try:
            while True:
                try:
                    yield stream_context.run(next, stream)
                except StopIteration:
                    return
        finally:
            stream_context.run(stream.close)

    def _stream_answer(
        self,
        question: str,
        *,
        request_id: str | None,
    ) -> Iterator[ChatEvent]:
        normalized_question = (question or "").strip()
        if not normalized_question:
            raise ValueError("question cannot be empty")

        with request_context(request_id=request_id), trace_span(
            "rag.query",
            attributes={"query.length": len(normalized_question)},
        ) as root_span:
            metrics = self.metrics_getter()
            total_started = perf_counter()
            llm_provider = self.settings.default_llm_provider
            active_operation = "rag.retrieve"
            generation_started: float | None = None
            first_token_received = False
            answer_parts: list[str] = []

            logger.info(
                "收到问答请求",
                event="query_received",
                operation="rag.query",
                status="started",
                query_length=len(normalized_question),
            )
            yield ChatEvent("status", {"stage": "retrieving"})

            try:
                retrieval_kwargs: dict[str, Any] = {
                    "top_k": self.settings.retrieval_top_k,
                    "score_threshold": self.settings.retrieval_score_threshold,
                }
                if self.lifecycle_service is not None:
                    retrieval_kwargs["result_predicate"] = (
                        self.lifecycle_service.active_metadata_predicate()
                    )
                retrieval_results = self.retriever.retrieve_semantic(
                    normalized_question,
                    **retrieval_kwargs,
                )

                if not retrieval_results:
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
                    yield ChatEvent("sources", {"items": []})
                    yield ChatEvent(
                        "done",
                        {
                            "status": "no_context",
                            "message": self.NO_CONTEXT_MESSAGE,
                        },
                    )
                    return

                active_operation = "rag.context.build"
                stage_started = perf_counter()
                with trace_span(
                    "rag.context.build",
                    attributes={"result.count": len(retrieval_results)},
                ):
                    sources = [
                        SourceReference.from_result(result).to_dict()
                        for result in retrieval_results
                    ]
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
                yield ChatEvent("sources", {"items": sources})
                yield ChatEvent("status", {"stage": "generating"})

                active_operation = "llm.generate"
                generation_started = perf_counter()
                logger.info(
                    "开始调用 LLM 生成回答",
                    event="generation_started",
                    operation=active_operation,
                    status="started",
                    provider=llm_provider,
                )
                with trace_span(
                    "llm.generate",
                    attributes={"provider": llm_provider},
                ):
                    for chunk in self.rag_generator.generate_answer_stream(
                        normalized_question,
                        retrieval_results,
                        config=GenerationConfig(
                            temperature=self.settings.llm_temperature,
                            max_tokens=self.settings.llm_max_tokens,
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
                        answer_parts.append(str(chunk))
                        yield ChatEvent("token", {"text": str(chunk)})

                if not answer_parts:
                    raise RuntimeError("LLM stream returned no text")

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
                    response_chars=len("".join(answer_parts)),
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
                    response_chars=len("".join(answer_parts)),
                )
                yield ChatEvent("done", {"status": "success"})
            except Exception as exc:
                mark_span_error(root_span, exc)
                elapsed = perf_counter() - total_started
                error_type = type(exc).__name__
                metrics.record_component_error(active_operation, error_type)
                if generation_started is not None:
                    generation_duration = perf_counter() - generation_started
                    if not first_token_received:
                        metrics.observe_first_token(
                            llm_provider, "error", generation_duration
                        )
                    metrics.observe_llm_total(
                        llm_provider, "error", generation_duration
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
                yield ChatEvent(
                    "error",
                    {
                        "code": (
                            "generation_interrupted"
                            if answer_parts
                            else "service_unavailable"
                        ),
                        "message": (
                            self.INTERRUPTION_MESSAGE
                            if answer_parts
                            else self.PUBLIC_ERROR_MESSAGE
                        ),
                        "partial": bool(answer_parts),
                        "retryable": True,
                    },
                )
