"""显式、幂等的结构化日志配置。

导入本模块不会创建目录或日志文件。应用入口必须显式调用 setup_logger()。
控制台默认输出便于开发者阅读的文本，文件默认输出一行一个 JSON 对象的 JSONL。
"""

from __future__ import annotations

import json
import re
import sys
import traceback
from pathlib import Path
from threading import RLock
from typing import Any, TextIO

from loguru import logger

from app.observability.context import get_request_id, get_trace_id

_STANDARD_FIELDS = (
    "service",
    "environment",
    "event",
    "operation",
    "request_id",
    "trace_id",
    "duration_ms",
    "status",
    "error_type",
)
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
)
_REDACTED = "[REDACTED]"
_SECRET_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+\-/]+=*"),
    re.compile(r"(?i)\b(sk-[A-Za-z0-9_-]{8,})\b"),
    re.compile(
        r"(?i)((?:api[_-]?key|authorization|password|secret|token)\s*[=:]\s*)"
        r"([^\s,;]+)"
    ),
)

_LOCK = RLock()
_HANDLER_IDS: list[int] = []
_BASE_FIELDS: dict[str, Any] = {
    "service": "rag-web",
    "environment": "development",
}


def _redact_text(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        if pattern.groups >= 2:
            redacted = pattern.sub(
                lambda match: f"{match.group(1)}{_REDACTED}", redacted
            )
        elif pattern.groups == 1 and pattern.pattern.lower().startswith("(?i)(bearer"):
            redacted = pattern.sub(
                lambda match: f"{match.group(1)}{_REDACTED}", redacted
            )
        else:
            redacted = pattern.sub(_REDACTED, redacted)
    return redacted


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _sanitize(value: Any, key: object | None = None) -> Any:
    if key is not None and _is_sensitive_key(key):
        return _REDACTED
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, dict):
        return {
            str(item_key): _sanitize(item_value, item_key)
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_sanitize(item) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _redact_text(str(value))


def _enrich_record(record: dict[str, Any]) -> None:
    """为每条日志补齐关联字段，并在日志进入 sink 前执行脱敏。"""

    record["message"] = _redact_text(str(record["message"]))
    sanitized_extra = _sanitize(dict(record["extra"]))
    record["extra"].clear()
    record["extra"].update(sanitized_extra)

    for key, value in _BASE_FIELDS.items():
        record["extra"].setdefault(key, value)

    request_id = get_request_id()
    trace_id = get_trace_id()
    if request_id is not None:
        record["extra"]["request_id"] = request_id
    if trace_id is not None:
        record["extra"]["trace_id"] = trace_id

    for field in _STANDARD_FIELDS:
        record["extra"].setdefault(field, None)

    exception = record.get("exception")
    if exception is not None and record["extra"].get("error_type") is None:
        exception_type = getattr(exception, "type", None)
        if exception_type is not None:
            record["extra"]["error_type"] = exception_type.__name__


def _json_formatter(record: dict[str, Any]) -> str:
    extra = dict(record["extra"])
    extra.pop("_serialized_json", None)
    payload: dict[str, Any] = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "message": record["message"],
        "module": record["name"],
        "function": record["function"],
        "line": record["line"],
    }
    for field in _STANDARD_FIELDS:
        payload[field] = extra.pop(field, None)
    if extra:
        payload["fields"] = _sanitize(extra)

    exception = record.get("exception")
    if exception is not None:
        formatted_exception = "".join(
            traceback.format_exception(
                exception.type,
                exception.value,
                exception.traceback,
            )
        )
        payload["exception"] = _redact_text(formatted_exception)

    serialized = json.dumps(payload, ensure_ascii=False, default=str)
    # 将 JSON 放进记录字段后再由固定模板输出，避免异常堆栈中的尖括号被
    # 转义成无效的 JSON 转义序列（例如 \<5 lines>）。
    record["extra"]["_serialized_json"] = serialized
    return "{extra[_serialized_json]}\n"


def _text_formatter(record: dict[str, Any]) -> str:
    request_id = record["extra"].get("request_id") or "-"
    return (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        f"request_id={request_id} | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>\n{exception}"
    )


def setup_logger(
    log_level: str = "INFO",
    log_file_path: str | Path | None = "./logs/rag_{time:YYYY-MM-DD}.jsonl",
    rotation: str = "500 MB",
    retention: str = "10 days",
    *,
    service: str = "rag-web",
    environment: str = "development",
    console_format: str = "text",
    file_format: str = "json",
    console_sink: TextIO | None = None,
) -> Any:
    """配置全局日志器。重复调用会替换旧 handler，不会重复输出。"""

    normalized_console_format = console_format.strip().lower()
    normalized_file_format = file_format.strip().lower()
    if normalized_console_format not in {"text", "json"}:
        raise ValueError("console_format 必须是 text 或 json")
    if normalized_file_format not in {"text", "json"}:
        raise ValueError("file_format 必须是 text 或 json")

    with _LOCK:
        _BASE_FIELDS.update(service=service, environment=environment)
        logger.remove()
        _HANDLER_IDS.clear()

        sink = console_sink if console_sink is not None else sys.stdout
        console_formatter = (
            _text_formatter
            if normalized_console_format == "text"
            else _json_formatter
        )
        _HANDLER_IDS.append(
            logger.add(
                sink,
                level=log_level.upper(),
                format=console_formatter,
                colorize=normalized_console_format == "text",
                backtrace=False,
                diagnose=False,
                enqueue=False,
            )
        )

        if log_file_path:
            path = Path(log_file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            file_formatter = (
                _json_formatter
                if normalized_file_format == "json"
                else _text_formatter
            )
            _HANDLER_IDS.append(
                logger.add(
                    str(path),
                    level="DEBUG",
                    format=file_formatter,
                    rotation=rotation,
                    retention=retention,
                    encoding="utf-8",
                    colorize=False,
                    backtrace=False,
                    diagnose=False,
                    enqueue=False,
                )
            )

    configured_logger = get_logger(__name__)
    configured_logger.info(
        "日志系统初始化完成",
        event="logging_initialized",
        operation="logging.setup",
        status="success",
    )
    return configured_logger


def get_logger(name: str | None = None) -> Any:
    """返回带统一字段补全和脱敏 patcher 的 Loguru logger。"""

    patched_logger = logger.patch(_enrich_record)
    if name:
        return patched_logger.bind(logger_name=name)
    return patched_logger


def reset_logger() -> None:
    """移除由本模块管理的 handler，主要用于测试隔离。"""

    with _LOCK:
        logger.remove()
        _HANDLER_IDS.clear()
        _BASE_FIELDS.update(service="rag-web", environment="development")
