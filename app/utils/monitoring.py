"""
性能监控工具
追踪函数执行时间和资源使用
"""

import time
import functools
from typing import Callable, Any
from app.utils.logger import get_logger

logger = get_logger(__name__)


def track_time(func: Callable) -> Callable:
    """
    装饰器：追踪函数执行时间
    
    Usage:
        @track_time
        def my_function():
            pass
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        start = time.time()
        func_name = f"{func.__module__}.{func.__name__}"
        
        try:
            result = func(*args, **kwargs)
            elapsed = time.time() - start
            
            logger.info(
                f"函数执行完成: {func_name}",
                elapsed_time=f"{elapsed:.3f}s"
            )
            
            return result
            
        except Exception as e:
            elapsed = time.time() - start
            logger.error(
                f"函数执行失败: {func_name}",
                elapsed_time=f"{elapsed:.3f}s",
                error=str(e)
            )
            raise
    
    return wrapper


class Timer:
    """
    上下文管理器：手动计时
    
    Usage:
        with Timer("数据库查询"):
            # do something
            pass
    """
    
    def __init__(self, name: str):
        self.name = name
        self.start_time = None
        self.elapsed = None
    
    def __enter__(self):
        self.start_time = time.time()
        logger.debug(f"开始计时: {self.name}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.elapsed = time.time() - self.start_time
        
        if exc_type is None:
            logger.info(
                f"计时完成: {self.name}",
                elapsed_time=f"{self.elapsed:.3f}s"
            )
        else:
            logger.error(
                f"计时中断: {self.name}",
                elapsed_time=f"{self.elapsed:.3f}s",
                error=str(exc_val)
            )


if __name__ == "__main__":
    """测试监控功能"""
    
    # 测试装饰器
    @track_time
    def test_function(sleep_time: float):
        time.sleep(sleep_time)
        return "完成"
    
    print("测试装饰器:")
    result = test_function(0.5)
    print(f"返回值: {result}\n")
    
    # 测试上下文管理器
    print("测试上下文管理器:")
    with Timer("模拟任务"):
        time.sleep(0.3)
    
    print("\n性能监控工具测试完成")
