"""RAG 系统可观测性基础设施。

本包只提供可观测性能力，导入时不会创建日志文件、启动端口或发送网络请求。
"""

from app.observability.context import (
    RequestContext,
    get_request_id,
    get_trace_id,
    request_context,
    trace_id_context,
)
from app.observability.logging import get_logger, setup_logger
from app.observability.tracing import (
    configure_tracing,
    get_tracing,
    mark_span_error,
    shutdown_tracing,
    trace_span,
)

__all__ = [
    "RequestContext",
    "configure_tracing",
    "get_logger",
    "get_request_id",
    "get_trace_id",
    "get_tracing",
    "mark_span_error",
    "request_context",
    "shutdown_tracing",
    "trace_id_context",
    "trace_span",
    "setup_logger",
]
