"""GUI 日志桥接与启动期缓冲。"""

from __future__ import annotations

from collections import deque
from threading import Lock

from loguru import logger

GUI_LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}"
GUI_LOG_MAX_LINES = 10000

_buffered_log_lines: deque[str] = deque(maxlen=GUI_LOG_MAX_LINES)
_buffer_lock = Lock()
_startup_log_state: dict[str, int | None] = {"sink_id": None}


def _normalize_log_line(message: str) -> str:
    """将 sink 输入规整为单行日志文本。

    Args:
        message: loguru sink 收到的原始文本。

    Returns:
        去掉尾部换行后的日志文本；若结果为空则返回空字符串。
    """
    return message.rstrip()


def _capture_startup_log_line(message: str) -> None:
    """缓存 GUI 启动早期日志。

    Args:
        message: loguru 已格式化后的日志文本。
    """
    normalized = _normalize_log_line(message)
    if not normalized:
        return

    with _buffer_lock:
        _buffered_log_lines.append(normalized)


def install_startup_log_buffer(*, level: str = "INFO") -> None:
    """安装 GUI 启动期日志缓冲 sink。

    Args:
        level: 需要缓存的最低日志级别。
    """
    remove_startup_log_buffer()
    _startup_log_state["sink_id"] = logger.add(
        _capture_startup_log_line,
        level=level,
        colorize=False,
        enqueue=False,
        format=GUI_LOG_FORMAT,
    )


def remove_startup_log_buffer() -> None:
    """移除 GUI 启动期日志缓冲 sink。"""
    sink_id = _startup_log_state["sink_id"]
    if sink_id is None:
        return

    try:
        logger.remove(sink_id)
    except ValueError:
        pass
    _startup_log_state["sink_id"] = None


def clear_buffered_log_lines() -> None:
    """清空当前已缓存的启动期日志。"""
    with _buffer_lock:
        _buffered_log_lines.clear()


def get_buffered_log_lines() -> tuple[str, ...]:
    """返回当前已缓存的启动期日志快照。"""
    with _buffer_lock:
        return tuple(_buffered_log_lines)
