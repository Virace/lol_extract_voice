"""执行中心日志缓冲与 sink 生命周期控制器。"""

from __future__ import annotations

from collections import deque

from loguru import logger
from PySide6.QtCore import QObject, QTimer, Signal

LOG_FLUSH_BATCH_INTERVAL_MS = 16


class _GuiLogTextRelay(QObject):
    """将 loguru 文本 sink 转发为 Qt 信号。"""

    message_received = Signal(str)

    def write(self, message: str) -> None:
        """接收 loguru 已格式化文本并转发。"""
        normalized = message.rstrip()
        if normalized:
            self.message_received.emit(normalized)

    def flush(self) -> None:
        """兼容 file-like sink 所需的空刷新接口。"""


class ExecutionLogController(QObject):
    """负责执行中心运行时日志的缓存、flush 与 sink 生命周期。"""

    log_lines_appended = Signal(object)

    def __init__(
        self,
        *,
        initial_lines: tuple[str, ...],
        max_lines: int,
        log_format: str,
        parent: QObject | None = None,
    ) -> None:
        """初始化执行中心日志控制器。"""
        super().__init__(parent)
        self._log_lines: deque[str] = deque(initial_lines, maxlen=max_lines)
        self._pending_log_lines: list[str] = []
        self._log_format = log_format
        self._runtime_log_sink_id: int | None = None
        self._log_flush_timer = QTimer(self)
        self._log_flush_timer.setSingleShot(True)
        self._log_flush_timer.setInterval(LOG_FLUSH_BATCH_INTERVAL_MS)
        self._log_flush_timer.timeout.connect(self.flush_pending_log_lines)
        self._runtime_log_relay = _GuiLogTextRelay(self)
        self._runtime_log_relay.message_received.connect(self.queue_runtime_log_line)

    def attach_runtime_log_sink(self, level: str = "INFO") -> None:
        """重新挂载 GUI 运行时日志 sink。"""
        self.detach_runtime_log_sink()
        logger.enable("lol_audio_unpack")
        self._runtime_log_sink_id = logger.add(
            self._runtime_log_relay,
            level=level.upper(),
            colorize=False,
            enqueue=True,
            format=self._log_format,
        )

    def current_log_text(self) -> str:
        """返回当前累计日志文本。"""
        self.flush_pending_log_lines()
        return "\n".join(self._log_lines)

    def queue_runtime_log_line(self, message: str) -> None:
        """缓存运行时日志，并在下一帧统一刷新。"""
        self._pending_log_lines.append(message)
        if not self._log_flush_timer.isActive():
            self._log_flush_timer.start(0)

    def flush_pending_log_lines(self) -> None:
        """将待刷新的日志批量合并进缓存。"""
        if not self._pending_log_lines:
            return

        pending_lines = tuple(self._pending_log_lines)
        self._pending_log_lines.clear()
        self._log_lines.extend(pending_lines)
        self.log_lines_appended.emit(pending_lines)

    def detach_runtime_log_sink(self, *_args: object) -> None:
        """移除当前 GUI 运行时日志 sink，避免重复注册。"""
        if self._runtime_log_sink_id is None:
            return

        try:
            logger.remove(self._runtime_log_sink_id)
        except ValueError:
            pass
        self._runtime_log_sink_id = None
