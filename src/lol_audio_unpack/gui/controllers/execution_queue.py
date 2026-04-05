"""执行中心队列状态机控制器。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from loguru import logger
from PySide6.QtCore import QObject, QThreadPool, Signal

from lol_audio_unpack.gui.controllers.contracts import (
    GuiLogMessage,
    GuiNotice,
    QueueProgressUpdate,
)
from lol_audio_unpack.gui.controllers.task_queue_store import (
    TaskQueueStore,
    build_task_queue_row_text,
)
from lol_audio_unpack.gui.service.task_runner import run_execution_task
from lol_audio_unpack.gui.task_models import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_RUNNING,
    TASK_STATUS_WAITING,
    ExecutionTaskDraft,
    ExecutionTaskProgress,
    ExecutionTaskResult,
    OutputStateRefreshRequest,
    QueuedExecutionTask,
)
from lol_audio_unpack.gui.workers import TaskWorker


def _build_output_state_refresh_request(
    task: QueuedExecutionTask,
    task_result: ExecutionTaskResult,
) -> OutputStateRefreshRequest:
    """根据任务快照和执行结果推导输出状态刷新范围。"""
    completed_steps = set(task_result.completed_steps)
    if not ({"音频解包", "事件映射"} & completed_steps):
        return OutputStateRefreshRequest(requires_full_refresh=True)

    task_params = task.draft.task_params
    champion_ids = (
        tuple(str(entity_id) for entity_id in task_params.champion_ids)
        if task_params.champion_ids is not None
        else ()
    )
    map_ids = (
        tuple(str(entity_id) for entity_id in task_params.map_ids)
        if task_params.map_ids is not None
        else ()
    )

    if not champion_ids and not map_ids:
        return OutputStateRefreshRequest(requires_full_refresh=True)

    return OutputStateRefreshRequest(champion_ids=champion_ids, map_ids=map_ids)


class ExecutionQueueController(QObject):
    """负责执行中心任务队列状态机与后台 worker 生命周期。"""

    task_running_changed = Signal(bool)
    task_queue_busy_changed = Signal(bool)
    progress_display_requested = Signal(object)
    feedback_requested = Signal(object)
    log_requested = Signal(object)
    output_state_refresh_requested = Signal(object)

    def __init__(
        self,
        *,
        build_task_item_tooltip: Callable[[QueuedExecutionTask], str],
        parent: QObject | None = None,
    ) -> None:
        """初始化执行队列控制器。"""
        super().__init__(parent)
        self._queue_store = TaskQueueStore()
        self._build_task_item_tooltip = build_task_item_tooltip
        self._draft_count = 0
        self._active_task_id: int | None = None
        self._active_worker: TaskWorker | None = None
        self._stage_completion_notifications: set[tuple[int, str]] = set()

    @property
    def active_task_id(self) -> int | None:
        """返回当前运行中的任务编号。"""
        return self._active_task_id

    def is_task_running(self) -> bool:
        """返回当前是否存在运行中的任务。"""
        return self._active_task_id is not None

    def has_active_background_work(self) -> bool:
        """返回执行中心是否仍持有运行中的后台任务。"""
        return bool(self._active_task_id is not None or self._active_worker is not None)

    def has_incomplete_tasks(self) -> bool:
        """返回当前队列中是否仍有未完成任务。"""
        counts = self.queue_status_counts()
        return counts[TASK_STATUS_RUNNING] + counts[TASK_STATUS_WAITING] + counts[TASK_STATUS_FAILED] > 0

    def draft_queue_size(self) -> int:
        """返回当前任务队列中的真实任务数。"""
        return self._queue_store.task_count()

    def queue_status_counts(self) -> dict[str, int]:
        """统计当前任务队列中的状态数量。"""
        return self._queue_store.status_counts()

    def find_task_by_id(self, task_id: int) -> QueuedExecutionTask | None:
        """按任务编号查找任务快照。"""
        return self._queue_store.find_task_by_id(task_id)

    def find_running_task(self) -> QueuedExecutionTask | None:
        """返回当前队列中处于运行态的任务快照。"""
        return self._queue_store.find_running_task()

    def enqueue_task(self, *, draft: ExecutionTaskDraft, summary: str) -> QueuedExecutionTask:
        """将任务草稿加入队列，并尽可能立即启动。"""
        self._draft_count += 1
        queued_task = self._queue_store.append_task(
            QueuedExecutionTask(task_id=self._draft_count, draft=draft, summary=summary)
        )
        row_text = build_task_queue_row_text(queued_task)

        self.log_requested.emit(GuiLogMessage(level="info", message=f"[队列] {row_text}"))
        started_task = self.start_next_waiting_task()
        if started_task is None:
            self.progress_display_requested.emit(
                QueueProgressUpdate(
                    status_text="状态：新任务已加入等待队列。",
                    note_text="0% · 当前显示任务队列状态。",
                    progress_current=0,
                    progress_total=1,
                )
            )
        elif self._active_task_id is not None:
            self.progress_display_requested.emit(QueueProgressUpdate(status_text="状态：任务已加入队列。"))
        else:
            self.progress_display_requested.emit(QueueProgressUpdate())

        self.feedback_requested.emit(
            GuiNotice(title="已加入任务队列", content=row_text, level="success")
        )
        return queued_task

    def update_task(self, task_id: int, **changes) -> QueuedExecutionTask:
        """更新任务快照。"""
        return self._queue_store.update_task(task_id, **changes)

    def start_next_waiting_task(self) -> QueuedExecutionTask | None:
        """将下一个等待中的任务提升为运行中。"""
        if self.find_running_task() is not None:
            return None

        for task in self._queue_store.tasks():
            if task.status != TASK_STATUS_WAITING:
                continue
            updated_task = self.update_task(
                task.task_id,
                status=TASK_STATUS_RUNNING,
                started_at=datetime.now(),
                progress_current=0,
                progress_total=0,
                progress_message="等待后台线程启动…",
                progress_detail=None,
                error_message="",
            )
            self._active_task_id = updated_task.task_id
            self.task_running_changed.emit(True)
            self.task_queue_busy_changed.emit(self.has_incomplete_tasks())
            self.log_requested.emit(
                GuiLogMessage(level="info", message=f"[队列] 已自动开始任务：{updated_task.summary}")
            )
            self.progress_display_requested.emit(
                QueueProgressUpdate(
                    status_text="状态：任务启动中。",
                    note_text="当前进度：准备中 · 等待后台线程启动。",
                    progress_current=0,
                    progress_total=1,
                )
            )
            self.start_task_worker(updated_task)
            return updated_task

        self.task_queue_busy_changed.emit(self.has_incomplete_tasks())
        return None

    def start_task_worker(self, task: QueuedExecutionTask) -> None:
        """为指定任务创建后台 worker 并提交到线程池。"""

        def run_with_signals(signals) -> ExecutionTaskResult:
            return run_execution_task(task, signals)

        worker = TaskWorker(run_with_signals, pass_signals=True)
        worker.signals.started.connect(lambda task_id=task.task_id: self.on_task_started(task_id))
        worker.signals.progress.connect(
            lambda progress, task_id=task.task_id: self.on_task_progress(task_id, progress)
        )
        worker.signals.finished.connect(
            lambda result, task_id=task.task_id: self.on_task_finished(task_id, result)
        )
        worker.signals.failed.connect(lambda error, task_id=task.task_id: self.on_task_failed(task_id, error))
        self._active_worker = worker
        QThreadPool.globalInstance().start(worker)

    def on_task_started(self, task_id: int) -> None:
        """处理后台任务真正启动后的摘要更新。"""
        task = self.find_task_by_id(task_id)
        if task is None:
            return
        logger.info(f"[队列] 任务 #{task_id} 已开始执行")
        self.progress_display_requested.emit(
            QueueProgressUpdate(
                status_text="状态：任务执行中。",
                note_text=f"当前进度：准备中 · {task.progress_message or '后台任务已开始执行。'}",
                progress_current=0,
                progress_total=1,
            )
        )

    def on_task_progress(self, task_id: int, progress: object) -> None:
        """接收后台任务进度并刷新队列状态。"""
        if not isinstance(progress, ExecutionTaskProgress):
            return

        updated_task = self.update_task(
            task_id,
            progress_current=max(progress.current, 0),
            progress_total=max(progress.total, 0),
            progress_message=progress.message,
            progress_detail=progress,
        )
        if progress.stage_finished and progress.stage_key == "extract":
            self._emit_extract_stage_notice(updated_task)
        if self._active_task_id == task_id:
            self.progress_display_requested.emit(QueueProgressUpdate())

    def _emit_extract_stage_notice(self, task: QueuedExecutionTask) -> None:
        """在解包阶段结束时发出一次性提示。"""
        notification_key = (task.task_id, "extract")
        if notification_key in self._stage_completion_notifications:
            return
        self._stage_completion_notifications.add(notification_key)
        stage_label = "音频解包阶段"
        content = f"任务 #{task.task_id} 已结束{stage_label}。"
        if task.draft.task_params.wav_enabled and task.draft.task_params.run_mapping:
            content = f"{content} 正在继续音频转码，完成后将继续事件映射。"
        elif task.draft.task_params.wav_enabled:
            content = f"{content} 正在继续音频转码。"
        elif task.draft.task_params.run_mapping:
            content = f"{content} 正在继续事件映射。"
        self.feedback_requested.emit(
            GuiNotice(title=f"{stage_label}已结束", content=content, level="info")
        )

    def on_task_finished(self, task_id: int, result: object) -> None:
        """处理后台任务成功完成后的状态收敛。"""
        task = self.find_task_by_id(task_id)
        if task is None:
            return

        task_result = (
            result
            if isinstance(result, ExecutionTaskResult)
            else ExecutionTaskResult(completed_steps=(), summary="任务执行完成。", duration_seconds=0.0)
        )
        completed_progress_detail = None
        if isinstance(task.progress_detail, ExecutionTaskProgress):
            completed_progress_detail = replace(
                task.progress_detail,
                current=max(task.progress_detail.total, 1),
                total=max(task.progress_detail.total, 1),
                message=task_result.summary,
            )

        updated_task = self.update_task(
            task_id,
            status=TASK_STATUS_COMPLETED,
            finished_at=datetime.now(),
            progress_current=max(task.progress_total, len(task_result.completed_steps), 1),
            progress_total=max(task.progress_total, len(task_result.completed_steps), 1),
            progress_message=task_result.summary,
            progress_detail=completed_progress_detail,
            result_summary=task_result.summary,
            error_message="",
        )
        self._after_task_stopped(task_id)
        logger.success(f"[队列] 任务 #{task_id} 执行完成：{task_result.summary}")
        self._advance_or_finish(updated_task, task_result)

    def on_task_failed(self, task_id: int, error: str) -> None:
        """处理后台任务失败后的状态收敛。"""
        task = self.find_task_by_id(task_id)
        if task is None:
            return

        failed_progress_detail = None
        if isinstance(task.progress_detail, ExecutionTaskProgress):
            failed_progress_detail = replace(task.progress_detail, message=error)
        progress_total = max(task.progress_total, 1)
        progress_current = min(task.progress_current, progress_total)
        updated_task = self.update_task(
            task_id,
            status=TASK_STATUS_FAILED,
            finished_at=datetime.now(),
            progress_current=progress_current,
            progress_total=progress_total,
            progress_message=error,
            progress_detail=failed_progress_detail,
            error_message=error,
        )
        self._after_task_stopped(task_id)
        logger.error(f"[队列] 任务 #{task_id} 执行失败：{error}")
        self._advance_or_finish(
            updated_task,
            ExecutionTaskResult(completed_steps=(), summary=error, duration_seconds=0.0),
        )
        self.feedback_requested.emit(GuiNotice(title="任务执行失败", content=error, level="error"))

    def _after_task_stopped(self, task_id: int) -> None:
        """清理一个任务结束后的通用运行态。"""
        self._active_task_id = None
        self._active_worker = None
        self._stage_completion_notifications = {
            entry for entry in self._stage_completion_notifications if entry[0] != task_id
        }
        self.task_running_changed.emit(False)

    def _advance_or_finish(self, task: QueuedExecutionTask, task_result: ExecutionTaskResult) -> None:
        """推进下一个等待任务，或收口当前队列状态。"""
        next_task = self.start_next_waiting_task()
        self.task_queue_busy_changed.emit(self.has_incomplete_tasks())
        if next_task is not None:
            self.progress_display_requested.emit(QueueProgressUpdate())
            return

        refresh_request = _build_output_state_refresh_request(task, task_result)
        if task.status == TASK_STATUS_COMPLETED:
            self.progress_display_requested.emit(
                QueueProgressUpdate(
                    status_text="状态：最近任务已完成。",
                    note_text=f"100% · {task.result_summary or task_result.summary}",
                    progress_current=1,
                    progress_total=1,
                )
            )
        else:
            self.progress_display_requested.emit(
                QueueProgressUpdate(
                    status_text="状态：最近任务执行失败。",
                    note_text=f"当前进度：{task.progress_current}/{task.progress_total} · {task.error_message or task_result.summary}",
                    progress_current=task.progress_current,
                    progress_total=task.progress_total,
                )
            )
        self.output_state_refresh_requested.emit(refresh_request)

    def clear_draft_queue(self) -> None:
        """清空当前任务队列中可直接移除的任务项。"""
        running_task = self.find_running_task()
        if running_task is not None:
            removed_count = self._queue_store.clear_non_running_tasks()
            if removed_count == 0:
                self.log_requested.emit(
                    GuiLogMessage(level="warning", message="[队列] 当前存在运行中的任务，暂不支持直接清空。")
                )
                self.feedback_requested.emit(
                    GuiNotice(
                        title="暂无法清空",
                        content="运行中的真实任务暂不支持直接移出队列，请等待任务结束后再清空。",
                        level="warning",
                    )
                )
                return

            self.log_requested.emit(
                GuiLogMessage(level="info", message=f"[队列] 已清空 {removed_count} 条非运行中任务。")
            )
            self.task_queue_busy_changed.emit(self.has_incomplete_tasks())
            self.progress_display_requested.emit(QueueProgressUpdate())
            return

        self.clear_mock_queue()
        self.log_requested.emit(GuiLogMessage(level="info", message="[队列] 已清空当前任务队列。"))

    def fill_mock_queue(self, *, count: int) -> str:
        """填充指定数量的 mock 队列项。"""
        if count <= 0:
            raise ValueError("queue fill 需要大于 0 的整数参数。")

        self._queue_store.clear_tasks()
        self._draft_count = count
        self._active_task_id = None
        self._active_worker = None
        self._stage_completion_notifications.clear()

        for task_id in range(1, count + 1):
            task = self._build_mock_task(task_id)
            self._queue_store.append_task(task)
            if task.status == TASK_STATUS_RUNNING and self._active_task_id is None:
                self._active_task_id = task_id

        self.task_running_changed.emit(self._active_task_id is not None)
        self.task_queue_busy_changed.emit(self.has_incomplete_tasks())
        self.progress_display_requested.emit(QueueProgressUpdate())
        return f"已填充 {count} 条 mock 队列项。"

    def _build_mock_task(self, task_id: int) -> QueuedExecutionTask:
        """构造单条调试用 mock 任务。"""
        if task_id == 1:
            status = TASK_STATUS_RUNNING
            progress_current = 1
            progress_total = 3
            progress_message = "Mock 任务运行中"
        elif task_id % 3 == 0:
            status = TASK_STATUS_COMPLETED
            progress_current = 1
            progress_total = 1
            progress_message = "Mock 任务已完成"
        else:
            status = TASK_STATUS_WAITING
            progress_current = 0
            progress_total = 0
            progress_message = ""

        return QueuedExecutionTask(
            task_id=task_id,
            draft=ExecutionTaskDraft(source="dev_console", source_summary="开发控制台填充的 mock 队列"),
            summary=f"Mock任务 {task_id} · 列表调试",
            status=status,
            progress_current=progress_current,
            progress_total=progress_total,
            progress_message=progress_message,
        )

    def clear_mock_queue(self) -> str:
        """清空当前调试队列并恢复空状态。"""
        self._queue_store.clear_tasks()
        self._active_task_id = None
        self._active_worker = None
        self._stage_completion_notifications.clear()
        self.task_running_changed.emit(False)
        self.task_queue_busy_changed.emit(self.has_incomplete_tasks())
        self.progress_display_requested.emit(QueueProgressUpdate())
        return "已清空当前队列。"

    def shutdown(self) -> None:
        """清理执行中心后台任务引用。"""
        self._active_task_id = None
        self._active_worker = None
        self._stage_completion_notifications.clear()

    def inspect_queue(self, *, builder_card_height: int) -> str:
        """返回当前队列的调试信息。"""
        counts = self.queue_status_counts()
        return "\n".join(
            [
                f"queue_count={self.draft_queue_size()}",
                f"active_task_id={self._active_task_id}",
                f"builder_card_height={builder_card_height}",
                (
                    f"running={counts[TASK_STATUS_RUNNING]} "
                    f"waiting={counts[TASK_STATUS_WAITING]} "
                    f"completed={counts[TASK_STATUS_COMPLETED]}"
                ),
            ]
        )
