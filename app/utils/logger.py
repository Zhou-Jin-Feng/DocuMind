"""日志兼容层。

新代码应优先从 app.observability.logging 导入。本模块保留旧导入路径，
且导入时不再自动初始化日志系统。
"""

from app.observability.logging import get_logger, reset_logger, setup_logger

__all__ = ["get_logger", "reset_logger", "setup_logger"]
