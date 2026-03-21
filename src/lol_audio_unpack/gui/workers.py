"""GUI 后台任务执行器。"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    """Signals emitted by background GUI workers."""

    started = Signal()
    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int, str)
    log = Signal(str)


class TaskWorker(QRunnable):
    """在线程池中执行后台任务。

    Args:
        fn: 后台执行函数。
        pass_signals: 为 ``True`` 时，将 ``WorkerSignals`` 作为唯一参数传入 ``fn``。
    """

    def __init__(self, fn: Callable[..., object], *, pass_signals: bool = False):
        super().__init__()
        self.fn = fn
        self._pass_signals = pass_signals
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        """执行后台函数并发出基础生命周期信号。"""
        self.signals.started.emit()
        try:
            result = self.fn(self.signals) if self._pass_signals else self.fn()
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(str(exc))
            return
        self.signals.finished.emit(result)
