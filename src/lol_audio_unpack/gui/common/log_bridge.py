"""GUI 日志桥接与启动期缓冲。"""

from __future__ import annotations

from collections import deque
from threading import Lock

from loguru import logger
from PySide6.QtCore import QtMsgType, qInstallMessageHandler
from pyvgmstream import LogLevel as PyVGMStreamLogLevel
from pyvgmstream import disable_log_callback, set_log_callback

GUI_LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}"
GUI_LOG_MAX_LINES = 10000

_buffered_log_lines: deque[str] = deque(maxlen=GUI_LOG_MAX_LINES)
_buffer_lock = Lock()
_startup_log_state: dict[str, int | None] = {"sink_id": None}
_qt_log_bridge_state: dict[str, object | None] = {"previous_handler": None, "installed": False}
_pyvgmstream_log_bridge_state: dict[str, bool] = {"installed": False}


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


def _resolve_qt_log_level(message_type: QtMsgType) -> str:
    """将 Qt 消息等级映射为 loguru 等级名。"""
    if message_type == QtMsgType.QtDebugMsg:
        return "DEBUG"
    if message_type == QtMsgType.QtInfoMsg:
        return "INFO"
    if message_type == QtMsgType.QtWarningMsg:
        return "WARNING"
    if message_type == QtMsgType.QtCriticalMsg:
        return "ERROR"
    return "CRITICAL"


def install_qt_message_bridge() -> None:
    """将 Qt 原生消息转发到 loguru。"""
    if _qt_log_bridge_state["installed"]:
        return

    def _qt_message_handler(message_type, context, message) -> None:
        category = getattr(context, "category", "") or "qt"
        logger.log(
            _resolve_qt_log_level(message_type),
            f"[Qt][{category}] {message}",
        )

    _qt_log_bridge_state["previous_handler"] = qInstallMessageHandler(_qt_message_handler)
    _qt_log_bridge_state["installed"] = True


def remove_qt_message_bridge() -> None:
    """恢复 Qt 原生日志处理器。"""
    previous_handler = _qt_log_bridge_state["previous_handler"]
    qInstallMessageHandler(previous_handler)
    _qt_log_bridge_state["previous_handler"] = None
    _qt_log_bridge_state["installed"] = False


def _resolve_pyvgmstream_log_level(level: PyVGMStreamLogLevel | int) -> str:
    """将 `pyvgmstream` 日志等级映射为 loguru 等级名。"""
    if level == PyVGMStreamLogLevel.INFO:
        return "INFO"
    return "DEBUG"


def install_pyvgmstream_log_bridge(
    *,
    set_log_callback_fn=set_log_callback,
    level: PyVGMStreamLogLevel = PyVGMStreamLogLevel.DEBUG,
) -> None:
    """将 `pyvgmstream` 上游回调日志转发到 loguru。"""
    if _pyvgmstream_log_bridge_state["installed"]:
        return

    def _log_callback(raw_level: PyVGMStreamLogLevel | int, message: str) -> None:
        logger.log(
            _resolve_pyvgmstream_log_level(raw_level),
            f"[pyvgmstream][{getattr(raw_level, 'name', raw_level)}] {message}",
        )

    set_log_callback_fn(_log_callback, level=level)
    _pyvgmstream_log_bridge_state["installed"] = True


def remove_pyvgmstream_log_bridge(*, disable_log_callback_fn=disable_log_callback) -> None:
    """关闭当前 `pyvgmstream` 日志桥接。"""
    disable_log_callback_fn()
    _pyvgmstream_log_bridge_state["installed"] = False


def clear_buffered_log_lines() -> None:
    """清空当前已缓存的启动期日志。"""
    with _buffer_lock:
        _buffered_log_lines.clear()


def get_buffered_log_lines() -> tuple[str, ...]:
    """返回当前已缓存的启动期日志快照。"""
    with _buffer_lock:
        return tuple(_buffered_log_lines)
