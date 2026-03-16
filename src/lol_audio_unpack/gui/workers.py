"""Qt worker scaffolding for future Python API integration."""

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
    """Run a callable in Qt's worker pool.

    Args:
        fn: Work function that will be executed in the background.
    """

    def __init__(self, fn: Callable[[], object]):
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        """Execute the worker function and emit basic lifecycle signals."""
        self.signals.started.emit()
        try:
            result = self.fn()
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(str(exc))
            return
        self.signals.finished.emit(result)
