"""执行中心任务独立进程 worker。"""

from __future__ import annotations

import multiprocessing as mp
from queue import Empty
from typing import Any

from PySide6.QtCore import QObject, QTimer

from lol_audio_unpack.gui.service.task_runner import run_execution_task
from lol_audio_unpack.gui.task_models import QueuedExecutionTask
from lol_audio_unpack.gui.workers import WorkerSignals

PROCESS_EVENT_STARTED = "started"
PROCESS_EVENT_FINISHED = "finished"
PROCESS_EVENT_FAILED = "failed"
PROCESS_EVENT_PROGRESS = "progress"


class _QueueSignalEmitter:
    """向跨进程队列写入单类事件。"""

    def __init__(self, event_name: str, event_queue) -> None:
        """保存事件名称与写入目标队列。"""
        self._event_name = event_name
        self._event_queue = event_queue

    def emit(self, payload: object = None) -> None:
        """将事件写入跨进程传输队列。"""
        self._event_queue.put((self._event_name, payload))


class _ProcessSignals:
    """为子进程任务构造与 GUI worker 对齐的 signal proxy。"""

    def __init__(self, event_queue) -> None:
        """为每类事件挂接单独的队列 emitter。"""
        self.started = _QueueSignalEmitter(PROCESS_EVENT_STARTED, event_queue)
        self.finished = _QueueSignalEmitter(PROCESS_EVENT_FINISHED, event_queue)
        self.failed = _QueueSignalEmitter(PROCESS_EVENT_FAILED, event_queue)
        self.progress = _QueueSignalEmitter(PROCESS_EVENT_PROGRESS, event_queue)


def _run_task_process(task: QueuedExecutionTask, event_queue) -> None:
    """在子进程中执行单条任务，并通过队列回传事件。"""
    signals = _ProcessSignals(event_queue)
    signals.started.emit()
    try:
        result = run_execution_task(task, signals)
    except Exception as exc:  # noqa: BLE001
        signals.failed.emit(str(exc))
        return
    signals.finished.emit(result)


class ExecutionProcessWorker(QObject):
    """用独立子进程承载单条执行中心任务。"""

    def __init__(
        self,
        task: QueuedExecutionTask,
        *,
        mp_context: Any | None = None,
        poll_interval_ms: int = 25,
        parent: QObject | None = None,
    ) -> None:
        """初始化子进程 worker。

        Args:
            task: 待执行的任务快照。
            mp_context: 可注入的 multiprocessing context；测试时可替换。
            poll_interval_ms: 主线程轮询事件队列的间隔。
            parent: Qt 父对象。
        """
        super().__init__(parent)
        self.signals = WorkerSignals()
        self._ctx = mp_context or mp.get_context("spawn")
        self._event_queue = self._ctx.Queue()
        self._process = self._ctx.Process(target=_run_task_process, args=(task, self._event_queue))
        self._transport_closed = False
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(poll_interval_ms)
        self._poll_timer.timeout.connect(self._pump_events)

    def start(self) -> None:
        """启动子进程并开始轮询事件。"""
        self._process.start()
        self._poll_timer.start()

    def isRunning(self) -> bool:  # noqa: N802
        """返回子进程是否仍在运行。"""
        return bool(self._process.is_alive())

    def requestInterruption(self) -> None:  # noqa: N802
        """保留与线程 worker 一致的接口，但不做额外操作。"""
        return None

    def quit(self) -> None:
        """保留与线程 worker 一致的接口，但不做额外操作。"""
        return None

    def wait(self, timeout_ms: int) -> bool:
        """在给定超时时间内等待子进程退出。"""
        self._process.join(timeout_ms / 1000)
        self._pump_events()
        finished = not self._process.is_alive()
        if finished:
            self._finalize_transport()
        return finished

    def terminate(self) -> None:
        """强制结束子进程并回收事件通道。"""
        if self._process.is_alive():
            self._process.terminate()
            self._process.join()
        self._finalize_transport()

    def _pump_events(self) -> None:
        """将子进程发回的事件转发为 Qt 信号。"""
        while True:
            try:
                event_name, payload = self._event_queue.get_nowait()
            except Empty:
                break

            if event_name == PROCESS_EVENT_STARTED:
                self.signals.started.emit()
            elif event_name == PROCESS_EVENT_PROGRESS:
                self.signals.progress.emit(payload)
            elif event_name == PROCESS_EVENT_FINISHED:
                self.signals.finished.emit(payload)
            elif event_name == PROCESS_EVENT_FAILED:
                self.signals.failed.emit(str(payload))

        if not self._process.is_alive():
            self._finalize_transport()

    def _finalize_transport(self) -> None:
        """关闭事件队列并停止轮询。"""
        if self._transport_closed:
            return
        self._poll_timer.stop()
        close = getattr(self._event_queue, "close", None)
        if callable(close):
            close()
        join_thread = getattr(self._event_queue, "join_thread", None)
        if callable(join_thread):
            join_thread()
        self._transport_closed = True
