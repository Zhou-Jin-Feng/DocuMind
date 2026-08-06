"""基于 contextvars 的请求关联上下文。"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator
from uuid import uuid4

_REQUEST_ID: ContextVar[str | None] = ContextVar("rag_request_id", default=None)
_TRACE_ID: ContextVar[str | None] = ContextVar("rag_trace_id", default=None)


@dataclass(frozen=True, slots=True)
class RequestContext:
    """一次请求中用于关联日志、指标和链路的标识。"""

    request_id: str
    trace_id: str


def _new_id() -> str:
    return uuid4().hex


def get_request_id() -> str | None:
    """返回当前执行上下文中的 request_id。"""

    return _REQUEST_ID.get()


def get_trace_id() -> str | None:
    """返回当前执行上下文中的 trace_id。"""

    return _TRACE_ID.get()


@contextmanager
def trace_id_context(trace_id: str) -> Iterator[str]:
    """临时覆盖当前 Trace ID，并在退出时恢复原值。"""

    token = _TRACE_ID.set(trace_id)
    try:
        yield trace_id
    finally:
        _TRACE_ID.reset(token)


@contextmanager
def request_context(
    request_id: str | None = None,
    trace_id: str | None = None,
) -> Iterator[RequestContext]:
    """创建并在退出时可靠清理一次请求的关联上下文。

    使用 ContextVar 而不是全局变量，确保并发线程和异步任务之间不会
    相互覆盖。嵌套使用时，退出内层上下文后会恢复外层标识。
    """

    context = RequestContext(
        request_id=request_id or _new_id(),
        trace_id=trace_id or _new_id(),
    )
    request_token = _REQUEST_ID.set(context.request_id)
    trace_token = _TRACE_ID.set(context.trace_id)
    try:
        yield context
    finally:
        _TRACE_ID.reset(trace_token)
        _REQUEST_ID.reset(request_token)
