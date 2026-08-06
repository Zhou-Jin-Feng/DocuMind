"""轻量性能计时兼容工具。

新业务链路优先使用 observability 模块中的指标与追踪能力。本模块保留
v1.2 的装饰器和上下文管理器 API，并确保流式生成器的耗时覆盖完整迭代。
"""

from __future__ import annotations

import functools
import inspect
from time import perf_counter
from typing import Any, Callable

from app.observability.logging import get_logger

logger = get_logger(__name__)


def _operation_name(func: Callable) -> str:
    return f"{func.__module__}.{func.__qualname__}"


def _log_completed(operation: str, started: float) -> None:
    logger.info(
        "函数执行完成",
        event="operation_completed",
        operation=operation,
        duration_ms=(perf_counter() - started) * 1000,
        status="success",
    )


def _log_failed(operation: str, started: float, exc: Exception) -> None:
    logger.exception(
        "函数执行失败",
        event="operation_failed",
        operation=operation,
        duration_ms=(perf_counter() - started) * 1000,
        status="error",
        error_type=type(exc).__name__,
    )


def track_time(func: Callable) -> Callable:
    """记录普通函数或生成器完整执行过程的耗时。"""

    operation = _operation_name(func)
    if inspect.isgeneratorfunction(func):

        @functools.wraps(func)
        def generator_wrapper(*args, **kwargs):
            started = perf_counter()
            try:
                yield from func(*args, **kwargs)
            except Exception as exc:
                _log_failed(operation, started, exc)
                raise
            else:
                _log_completed(operation, started)

        return generator_wrapper

    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        started = perf_counter()
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            _log_failed(operation, started, exc)
            raise
        _log_completed(operation, started)
        return result

    return wrapper


class Timer:
    """使用单调高精度时钟记录一个代码块的耗时。"""

    def __init__(self, name: str):
        self.name = name
        self.start_time: float | None = None
        self.elapsed: float | None = None

    def __enter__(self):
        self.start_time = perf_counter()
        logger.debug(
            "开始计时",
            event="timer_started",
            operation=self.name,
            status="started",
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is None:
            return False
        self.elapsed = perf_counter() - self.start_time
        fields = {
            "event": "timer_completed" if exc_type is None else "timer_failed",
            "operation": self.name,
            "duration_ms": self.elapsed * 1000,
            "status": "success" if exc_type is None else "error",
            "error_type": exc_type.__name__ if exc_type is not None else None,
        }
        if exc_type is None:
            logger.info("计时完成", **fields)
        else:
            logger.error("计时中断", **fields)
        return False
