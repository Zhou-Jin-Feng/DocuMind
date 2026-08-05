"""
统一日志管理
使用 loguru 替代标准 logging 和 rich.console
"""

import sys
from pathlib import Path
from loguru import logger


def setup_logger(
    log_level: str = "INFO",
    log_file_path: str = "./logs/rag_{time:YYYY-MM-DD}.log",
    rotation: str = "500 MB",
    retention: str = "10 days"
):
    """
    配置全局日志器
    
    Args:
        log_level: 日志级别
        log_file_path: 日志文件路径（支持 loguru 时间格式占位符）
        rotation: 日志轮转大小
        retention: 日志保留时间
    """
    # 移除默认handler
    logger.remove()
    
    # 控制台输出（彩色，适合开发）
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=log_level,
        colorize=True
    )
    
    # 确保日志目录存在（使用固定路径，不包含时间占位符）
    log_dir = Path("./logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 文件输出（结构化，适合生产）
    # loguru 会自动处理 {time:YYYY-MM-DD} 占位符
    logger.add(
        log_file_path,
        rotation=rotation,
        retention=retention,
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        encoding="utf-8"
    )
    
    logger.info("日志系统初始化完成")
    return logger


def get_logger(name: str = None):
    """
    获取logger实例
    
    Args:
        name: 模块名称（通常传入 __name__）
        
    Returns:
        绑定了名称的logger
    """
    if name:
        return logger.bind(name=name)
    return logger


# 默认初始化（可以在应用启动时重新配置）
setup_logger()


if __name__ == "__main__":
    """测试日志功能"""
    log = get_logger(__name__)
    
    log.debug("这是DEBUG级别日志")
    log.info("这是INFO级别日志")
    log.warning("这是WARNING级别日志")
    log.error("这是ERROR级别日志")
    
    # 测试结构化日志
    log.info("用户查询", query="什么是RAG", top_k=3)
    log.info("检索完成", results_count=5, elapsed_time="0.5s")
    
    print("\n日志已同时输出到控制台和文件: ./logs/")
