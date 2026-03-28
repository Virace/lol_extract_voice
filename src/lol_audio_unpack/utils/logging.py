"""集中管理项目的 Loguru 日志初始化与辅助能力。"""

import sys
import time
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any

from loguru import logger

from lol_audio_unpack.utils.common import format_duration


class LoggingConfiguration:
    """Loguru 日志配置工具（无外部依赖，可独立使用）"""

    @staticmethod
    def _resolve_console_sink(stream: Any) -> Any:
        """将标准流对象转换为可安全传给 Loguru 的 sink。

        Args:
            stream: 标准输出或错误流对象。

        Returns:
            Any: 原始流对象；若传入 ``None``，则返回一个丢弃消息的 callable sink，
                用于兼容 PyInstaller ``windowed`` / ``noconsole`` 下标准流缺失的场景。
        """

        if stream is not None:
            return stream
        return lambda _message: None

    @staticmethod
    def _add_handler_with_enqueue_fallback(*args, **kwargs) -> None:
        """优先启用 enqueue，失败时回退为非 enqueue。"""
        try:
            logger.add(*args, **kwargs)
        except (OSError, PermissionError):
            fallback_kwargs = dict(kwargs)
            fallback_kwargs["enqueue"] = False
            logger.add(*args, **fallback_kwargs)
            logger.warning("日志队列初始化失败，已回退为非 enqueue 模式。")

    @staticmethod
    def setup_logging(
        *,
        dev_mode: bool = False,
        log_level: str = "INFO",
        file_log_level: str = "DEBUG",
        log_file_path: Path | str | None = None,
        show_function_info: bool = True,
    ) -> None:
        """
        设置日志配置

        :param dev_mode: 是否为开发模式（影响diagnose参数）
        :param log_level: 控制台日志级别
        :param file_log_level: 文件日志级别
        :param log_file_path: 日志文件路径，None表示不记录文件日志
        :param show_function_info: 是否显示函数名、行号等信息
        """
        # 移除默认处理器
        logger.remove()

        # 控制台日志格式
        if show_function_info:
            console_format = (
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>"
            )
        else:
            console_format = (
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>"
            )

        # 添加控制台日志处理器
        LoggingConfiguration._add_handler_with_enqueue_fallback(
            LoggingConfiguration._resolve_console_sink(sys.stderr),
            level=log_level.upper(),
            format=console_format,
            backtrace=True,
            diagnose=dev_mode,  # 开发模式显示变量值，生产模式不显示敏感信息
            colorize=True,
            enqueue=True,  # 线程安全
        )

        # 如果指定了文件日志路径，添加文件日志处理器
        if log_file_path:
            log_path = Path(log_file_path)
            # log_path 指向目录（例如 output/logs），懒创建模式下需显式创建该目录。
            log_path.mkdir(parents=True, exist_ok=True)

            # 文件日志格式（更详细，包含完整路径信息）
            file_format = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}"

            LoggingConfiguration._add_handler_with_enqueue_fallback(
                log_path / "{time:YYYY-MM-DD_HH-mm-ss}.log",
                level=file_log_level.upper(),
                format=file_format,
                rotation="100 MB",  # 当文件达到100MB时轮转
                retention=10,  # 保留最近10份日志文件
                compression="zip",  # 压缩旧日志文件
                backtrace=True,
                diagnose=dev_mode,
                enqueue=True,
            )

    @staticmethod
    def catch_and_log(
        exception_type: type = Exception,
        reraise: bool = True,
        level: str = "ERROR",
        message: str | None = None,
    ):
        """
        异常捕获装饰器

        :param exception_type: 要捕获的异常类型
        :param reraise: 是否重新抛出异常
        :param level: 日志级别
        :param message: 自定义错误消息
        """

        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except exception_type as e:
                    error_msg = message or f"函数 {func.__name__} 执行失败"
                    logger.opt(exception=True).log(level, f"{error_msg}: {str(e)}")
                    if reraise:
                        raise
                    return None

            return wrapper

        return decorator

    @staticmethod
    def performance_monitor(threshold_ms: float = 0, level: str = "DEBUG"):
        """
        性能监控装饰器

        :param threshold_ms: 性能阈值（毫秒）。0表示不进行阈值警告，只记录执行时间
        :param level: 正常情况下的日志级别
        """

        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    duration_ms = (time.time() - start_time) * 1000

                    # 格式化耗时显示
                    duration_display = format_duration(duration_ms)

                    # 记录性能信息
                    if threshold_ms > 0 and duration_ms > threshold_ms:
                        # 有阈值且超过阈值，记录警告
                        threshold_display = format_duration(threshold_ms)
                        logger.warning(
                            f"函数 {func.__name__} 执行耗时较长: {duration_display} (超过阈值 {threshold_display})"
                        )
                    else:
                        # 无阈值或未超过阈值，正常记录
                        logger.log(level, f"函数 {func.__name__} 执行完成，耗时: {duration_display}")
                    return result
                except Exception:
                    duration_ms = (time.time() - start_time) * 1000
                    duration_display = format_duration(duration_ms)
                    logger.opt(exception=True).error(f"函数 {func.__name__} 执行失败，耗时: {duration_display}")
                    raise

            return wrapper

        return decorator

    @staticmethod
    def create_context_logger(context: dict[str, Any]):
        """
        创建带有上下文信息的日志器

        :param context: 上下文信息字典
        :returns: 绑定了上下文的logger
        """
        return logger.bind(**context)


# 便捷的全局装饰器和函数
catch_and_log = LoggingConfiguration.catch_and_log
performance_monitor = LoggingConfiguration.performance_monitor


def trace_function_calls(func: Callable) -> Callable:
    """
    函数调用追踪装饰器
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        # 使用 TRACE 级别记录函数入口
        logger.opt(depth=1).trace(f"→ 进入函数 {func.__name__}")
        try:
            result = func(*args, **kwargs)
            logger.opt(depth=1).trace(f"← 退出函数 {func.__name__}")
            return result
        except Exception:
            logger.opt(depth=1, exception=True).trace(f"✗ 函数 {func.__name__} 异常退出")
            raise

    return wrapper


def log_level_context(level: str):
    """
    临时改变日志级别的上下文管理器
    """

    class LogLevelContext:
        def __init__(self, target_level: str):
            self.target_level = target_level
            self.original_handlers = []

        def __enter__(self):
            # 保存当前处理器配置
            self.original_handlers = logger._core.handlers.copy()
            # 临时修改级别
            logger.remove()
            logger.add(
                LoggingConfiguration._resolve_console_sink(sys.stderr),
                level=self.target_level,
                format="<level>{level: <8}</level> | <level>{message}</level>",
                colorize=True,
            )
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            # 恢复原始配置
            logger.remove()
            for handler in self.original_handlers.values():
                logger.add(**handler._sink, **handler._kwargs)

    return LogLevelContext(level)


# 快捷记录各种统计信息的函数
def log_statistics(category: str, operation: str, **stats):
    """
    记录统计信息的快捷函数

    :param category: 统计类别（如 'champion', 'map', 'file'）
    :param operation: 操作类型（如 'processed', 'success', 'failed'）
    :param stats: 额外的统计数据
    """
    # 使用自定义日志等级记录统计信息
    logger.bind(category=category, operation=operation, **stats).info("统计信息")


def log_performance(func_name: str, duration_ms: float, **metadata):
    """
    记录性能信息的快捷函数

    :param func_name: 函数名
    :param duration_ms: 执行时间（毫秒）
    :param metadata: 额外的元数据
    """
    logger.bind(function=func_name, duration_ms=duration_ms, **metadata).debug("性能信息")


# 为了向后兼容，保留一些常用的便捷函数
def setup_logging(**kwargs):
    """便捷的设置函数，直接调用LoggingConfiguration.setup_logging"""
    return LoggingConfiguration.setup_logging(**kwargs)


def create_context_logger(**context):
    """便捷的上下文日志器创建函数"""
    return LoggingConfiguration.create_context_logger(context)
