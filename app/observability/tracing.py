"""OpenTelemetry 链路追踪封装。

使用应用私有 TracerProvider，不会覆盖进程全局 Provider。模块导入本身
不会创建网络导出器；只有显式启用且配置 OTLP endpoint 时才会导出。
"""

from __future__ import annotations

from contextlib import contextmanager
from threading import RLock
from typing import Iterator, Mapping

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
)
from opentelemetry.trace import (
    NoOpTracerProvider,
    Span,
    SpanKind,
    Status,
    StatusCode,
)

from app.observability.context import trace_id_context

SpanAttribute = str | bool | int | float | list[str] | list[bool] | list[int] | list[float]

_SENSITIVE_ATTRIBUTE_NAMES = {
    "document",
    "document_id",
    "file_path",
    "query",
    "request_id",
    "trace_id",
}

_SENSITIVE_ATTRIBUTE_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "content",
    "document_text",
    "file_name",
    "filename",
    "password",
    "prompt",
    "query_text",
    "secret",
    "token",
)


def _safe_attributes(
    attributes: Mapping[str, SpanAttribute] | None,
) -> dict[str, SpanAttribute]:
    """过滤可能包含原文、凭据或高基数标识的 Span 属性。"""

    if not attributes:
        return {}
    safe: dict[str, SpanAttribute] = {}
    for key, value in attributes.items():
        normalized_key = key.lower().replace("-", "_").replace(".", "_")
        if normalized_key in _SENSITIVE_ATTRIBUTE_NAMES or any(
            part in normalized_key for part in _SENSITIVE_ATTRIBUTE_PARTS
        ):
            continue
        safe[str(key)] = value
    return safe


class TracingManager:
    """管理应用私有 TracerProvider 及可选 OTLP 导出器。"""

    def __init__(
        self,
        enabled: bool = False,
        service_name: str = "rag-web",
        environment: str = "development",
        endpoint: str | None = None,
        span_exporter: SpanExporter | None = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.service_name = service_name
        self.environment = environment
        self.endpoint = endpoint or None
        self._provider: TracerProvider | NoOpTracerProvider

        if not self.enabled:
            self._provider = NoOpTracerProvider()
            self._tracer = self._provider.get_tracer(__name__)
            return

        resource = Resource.create(
            {
                "service.name": service_name,
                "deployment.environment.name": environment,
            }
        )
        provider = TracerProvider(resource=resource, shutdown_on_exit=False)
        if span_exporter is not None:
            provider.add_span_processor(SimpleSpanProcessor(span_exporter))
        elif self.endpoint:
            exporter = OTLPSpanExporter(endpoint=self.endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))

        self._provider = provider
        self._tracer = provider.get_tracer(
            "documind.observability",
            "1.3",
        )

    @contextmanager
    def span(
        self,
        name: str,
        *,
        attributes: Mapping[str, SpanAttribute] | None = None,
        kind: SpanKind = SpanKind.INTERNAL,
    ) -> Iterator[Span]:
        """创建 Span；关闭追踪时透明退化为 NoOp Span。"""

        with self._tracer.start_as_current_span(
            name,
            kind=kind,
            attributes=_safe_attributes(attributes),
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            span_context = span.get_span_context()
            trace_id = (
                format(span_context.trace_id, "032x")
                if span_context.is_valid
                else None
            )
            try:
                if trace_id is None:
                    yield span
                else:
                    with trace_id_context(trace_id):
                        yield span
            except Exception as exc:
                mark_span_error(span, exc)
                raise

    def shutdown(self) -> None:
        """刷新并关闭当前 SDK Provider；NoOp Provider 无需处理。"""

        if isinstance(self._provider, TracerProvider):
            self._provider.shutdown()


_manager_lock = RLock()
_manager = TracingManager()


def configure_tracing(
    enabled: bool = False,
    *,
    service_name: str = "rag-web",
    environment: str = "development",
    endpoint: str | None = None,
    span_exporter: SpanExporter | None = None,
) -> TracingManager:
    """显式配置追踪，不修改 OpenTelemetry 全局 TracerProvider。"""

    global _manager
    new_manager = TracingManager(
        enabled=enabled,
        service_name=service_name,
        environment=environment,
        endpoint=endpoint,
        span_exporter=span_exporter,
    )
    with _manager_lock:
        previous = _manager
        _manager = new_manager
    previous.shutdown()
    return new_manager


def get_tracing() -> TracingManager:
    """返回当前追踪管理器。"""

    return _manager


@contextmanager
def trace_span(
    name: str,
    *,
    attributes: Mapping[str, SpanAttribute] | None = None,
    kind: SpanKind = SpanKind.INTERNAL,
) -> Iterator[Span]:
    """使用当前管理器创建一个 Span。"""

    with get_tracing().span(name, attributes=attributes, kind=kind) as span:
        yield span


def mark_span_error(span: Span | None, exc: BaseException) -> None:
    """仅记录异常类型并标记 ERROR，避免泄露异常消息和业务原文。"""

    if span is None or not span.is_recording():
        return
    span.set_attribute("error.type", type(exc).__name__)
    span.set_status(Status(StatusCode.ERROR))


def shutdown_tracing() -> None:
    """关闭当前追踪管理器并恢复为禁用状态。"""

    global _manager
    with _manager_lock:
        previous = _manager
        _manager = TracingManager()
    previous.shutdown()
