"""执行中心队列状态机控制器。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from loguru import logger
from PySide6.QtCore import QObject, QThreadPool, Signal
from PySide6.QtWidgets import QListWidgetItem

from lol_audio_unpack.gui.controllers.contracts import (
    GuiLogMessage,
    GuiNotice,
    QueueProgressUpdate,
)
from lol_audio_unpack.gui.service.task_runner import run_execution_task
from lol_audio_unpack.gui.task_models import (
    TASK_STATUS_CANCELLED,
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
from lol_audio_unpack.gui.view.execution.task_queue_panel import (
    QUEUE_VISIBLE_ROW_COUNT,
    TASK_ITEM_ROLE,
    TaskQueuePanel,
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

    return OutputStateRefreshRequest(
        champion_ids=champion_ids,
        map_ids=map_ids,
    )


class ExecutionQueueController(QObject):
    """负责执行中心任务队列状态机与后台 worker 生命周期。"""

    task_running_changed = Signal(bool)
    task_queue_busy_changed = Signal(bool)
    progress_display_requested = Signal(object)
    feedback_requested = Signal(object)
    log_requested = Signal(object)
    output_state_refresh_requested = Signal(object)

    def __init__(  # noqa: PLR0913
        self,
        *,
        queue_panel: TaskQueuePanel,
        build_task_item_tooltip: Callable[[QueuedExecutionTask], str],
        parent: QObject | None = None,
    ) -> None:
        """初始化执行队列控制器。

        Args:
            queue_panel: 队列列表面板。
            build_task_item_tooltip: 构造任务 tooltip 的回调。
            parent: 父级对象。
        """
        super().__init__(parent)
        self._queue_panel = queue_panel
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
        return self._active_task_id is not None or self._active_worker is not None

    def has_incomplete_tasks(self) -> bool:
        """返回当前队列中是否仍有未完成任务。"""
        counts = self.queue_status_counts()
        return (
            counts[TASK_STATUS_RUNNING]
            + counts[TASK_STATUS_WAITING]
            + counts[TASK_STATUS_FAILED]
            > 0
        )

    def draft_queue_size(self) -> int:
        """返回当前任务队列中的真实任务数。"""
        return self._queue_panel.task_count()

    def queue_status_counts(self) -> dict[str, int]:
        """统计当前任务队列中的状态数量。"""
        return self._queue_panel.status_counts()

    def find_task_item_by_id(self, task_id: int) -> QListWidgetItem | None:
        """按任务编号查找对应的列表项。"""
        return self._queue_panel.find_task_item_by_id(task_id)

    def find_running_task_item(self) -> QListWidgetItem | None:
        """返回当前队列中处于运行态的任务项。"""
        return self._queue_panel.find_running_task_item()

    def enqueue_task(self, *, draft: ExecutionTaskDraft, summary: str) -> QueuedExecutionTask:
        """将任务草稿加入队列，并尽可能立即启动。

        Args:
            draft: 任务草稿。
            summary: 任务摘要。

        Returns:
            QueuedExecutionTask: 新加入队列的任务快照。
        """
        self._draft_count += 1
        queued_task = QueuedExecutionTask(
            task_id=self._draft_count,
            draft=draft,
            summary=summary,
        )
        item = self._queue_panel.append_task(
            queued_task,
            tooltip=self._build_task_item_tooltip(queued_task),
        )
        row_text = item.text()

        self.log_requested.emit(
            GuiLogMessage(level="info", message=f"[队列] {row_text}")
        )
        started_item = self.start_next_waiting_task()
        if started_item is None:
            self.progress_display_requested.emit(
                QueueProgressUpdate(
                    status_text="状态：新任务已加入等待队列。",
                    note_text="0% · 当前显示任务队列状态。",
                    progress_current=0,
                    progress_total=1,
                )
            )
        elif self._active_task_id is not None:
            self.progress_display_requested.emit(
                QueueProgressUpdate(status_text="状态：任务已加入队列。")
            )
        else:
            self.progress_display_requested.emit(QueueProgressUpdate())

        self.feedback_requested.emit(
            GuiNotice(title="已加入任务队列", content=row_text, level="success")
        )
        return queued_task

    def update_queue_item(  # noqa: PLR0913
        self,
        item: QListWidgetItem,
        *,
        status: str | None = None,
        summary: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        progress_current: int | None = None,
        progress_total: int | None = None,
        progress_message: str | None = None,
        progress_detail: ExecutionTaskProgress | None = None,
        result_summary: str | None = None,
        error_message: str | None = None,
    ) -> QueuedExecutionTask:
        """更新任务项模型并同步显示。"""
        payload = item.data(TASK_ITEM_ROLE)
        if not isinstance(payload, QueuedExecutionTask):
            raise TypeError("任务队列项缺少有效的任务模型。")

        updated_payload = replace(
            payload,
            status=status if status is not None else payload.status,
            summary=summary if summary is not None else payload.summary,
            started_at=started_at if started_at is not None else payload.started_at,
            finished_at=finished_at if finished_at is not None else payload.finished_at,
            progress_current=progress_current if progress_current is not None else payload.progress_current,
            progress_total=progress_total if progress_total is not None else payload.progress_total,
            progress_message=progress_message if progress_message is not None else payload.progress_message,
            progress_detail=progress_detail if progress_detail is not None else payload.progress_detail,
            result_summary=result_summary if result_summary is not None else payload.result_summary,
            error_message=error_message if error_message is not None else payload.error_message,
        )
        item.setData(TASK_ITEM_ROLE, updated_payload)
        self._queue_panel.update_task(
            item,
            updated_payload,
            tooltip=self._build_task_item_tooltip(updated_payload),
        )
        return updated_payload

    def start_next_waiting_task(self) -> QListWidgetItem | None:
        """将下一个等待中的任务提升为运行中。"""
        if self.find_running_task_item() is not None:
            return None

        for item in self._queue_panel.task_items():
            payload = item.data(TASK_ITEM_ROLE)
            if isinstance(payload, QueuedExecutionTask) and payload.status == TASK_STATUS_WAITING:
                updated_payload = self.update_queue_item(
                    item,
                    status=TASK_STATUS_RUNNING,
                    started_at=datetime.now(),
                    progress_current=0,
                    progress_total=0,
                    progress_message="等待后台线程启动…",
                    progress_detail=None,
                    error_message="",
                )
                self._active_task_id = updated_payload.task_id
                self.task_running_changed.emit(True)
                self.task_queue_busy_changed.emit(self.has_incomplete_tasks())
                self.log_requested.emit(
                    GuiLogMessage(
                        level="info",
                        message=f"[队列] 已自动开始任务：{updated_payload.summary}",
                    )
                )
                self.progress_display_requested.emit(
                    QueueProgressUpdate(
                        status_text="状态：任务启动中。",
                        note_text="当前进度：准备中 · 等待后台线程启动。",
                        progress_current=0,
                        progress_total=1,
                    )
                )
                self.start_task_worker(updated_payload)
                return item

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
        """处理后台任务真正启动后的 UI 摘要更新。"""
        item = self.find_task_item_by_id(task_id)
        if item is None:
            return
        payload = item.data(TASK_ITEM_ROLE)
        if not isinstance(payload, QueuedExecutionTask):
            return
        self.progress_display_requested.emit(
            QueueProgressUpdate(
                status_text="状态：任务执行中。",
                note_text=f"当前进度：准备中 · {payload.progress_message or '后台任务已开始执行。'}",
                progress_current=0,
                progress_total=1,
            )
        )

    def on_task_progress(self, task_id: int, progress: object) -> None:
        """接收后台任务进度并刷新队列状态。"""
        if not isinstance(progress, ExecutionTaskProgress):
            return
        item = self.find_task_item_by_id(task_id)
        if item is None:
            return
        self.update_queue_item(
            item,
            progress_current=max(progress.current, 0),
            progress_total=max(progress.total, 0),
            progress_message=progress.message,
            progress_detail=progress,
        )
        if progress.stage_finished and progress.stage_key == "extract":
            notification_key = (task_id, progress.stage_key)
            if notification_key not in self._stage_completion_notifications:
                self._stage_completion_notifications.add(notification_key)
                payload = item.data(TASK_ITEM_ROLE)
                if isinstance(payload, QueuedExecutionTask):
                    content = f"任务 #{task_id} 已结束音频解包阶段。"
                    if payload.draft.task_params.run_mapping:
                        content = f"{content} 正在继续事件映射。"
                else:
                    content = f"任务 #{task_id} 已结束音频解包阶段。"
                self.feedback_requested.emit(
                    GuiNotice(title="音频解包阶段已结束", content=content, level="info")
                )
        if self._active_task_id == task_id:
            self.progress_display_requested.emit(QueueProgressUpdate())

    def on_task_finished(self, task_id: int, result: object) -> None:
        """处理后台任务成功完成后的状态收敛。"""
        item = self.find_task_item_by_id(task_id)
        if item is None:
            return

        task_result = (
            result
            if isinstance(result, ExecutionTaskResult)
            else ExecutionTaskResult(completed_steps=(), summary="任务执行完成。", duration_seconds=0.0)
        )
        payload = item.data(TASK_ITEM_ROLE)
        if not isinstance(payload, QueuedExecutionTask):
            return

        completed_progress_detail = (
            replace(
                payload.progress_detail,
                current=max(payload.progress_detail.total, 1),
                total=max(payload.progress_detail.total, 1),
                message=task_result.summary,
            )
            if isinstance(payload.progress_detail, ExecutionTaskProgress)
            else None
        )
        updated_payload = self.update_queue_item(
            item,
            status=TASK_STATUS_COMPLETED,
            finished_at=datetime.now(),
            progress_current=max(payload.progress_total, len(task_result.completed_steps), 1),
            progress_total=max(payload.progress_total, len(task_result.completed_steps), 1),
            progress_message=task_result.summary,
            progress_detail=completed_progress_detail,
            result_summary=task_result.summary,
            error_message="",
        )
        self._active_task_id = None
        self._active_worker = None
        self._stage_completion_notifications = {
            entry for entry in self._stage_completion_notifications if entry[0] != task_id
        }
        self.task_running_changed.emit(False)
        next_item = self.start_next_waiting_task()
        self.task_queue_busy_changed.emit(self.has_incomplete_tasks())
        if next_item is None:
            refresh_request = _build_output_state_refresh_request(updated_payload, task_result)
            self.progress_display_requested.emit(
                QueueProgressUpdate(
                    status_text="状态：最近任务已完成。",
                    note_text=f"100% · {updated_payload.result_summary or task_result.summary}",
                    progress_current=1,
                    progress_total=1,
                )
            )
            self.output_state_refresh_requested.emit(refresh_request)
        else:
            self.progress_display_requested.emit(QueueProgressUpdate())

    def on_task_failed(self, task_id: int, error: str) -> None:
        """处理后台任务失败后的状态收敛。"""
        item = self.find_task_item_by_id(task_id)
        if item is None:
            return

        payload = item.data(TASK_ITEM_ROLE)
        if not isinstance(payload, QueuedExecutionTask):
            return

        progress_total = max(payload.progress_total, 1)
        progress_current = min(payload.progress_current, progress_total)
        failed_progress_detail = (
            replace(payload.progress_detail, message=error)
            if isinstance(payload.progress_detail, ExecutionTaskProgress)
            else None
        )
        updated_payload = self.update_queue_item(
            item,
            status=TASK_STATUS_FAILED,
            finished_at=datetime.now(),
            progress_current=progress_current,
            progress_total=progress_total,
            progress_message=error,
            progress_detail=failed_progress_detail,
            error_message=error,
        )
        self._active_task_id = None
        self._active_worker = None
        self._stage_completion_notifications = {
            entry for entry in self._stage_completion_notifications if entry[0] != task_id
        }
        self.task_running_changed.emit(False)
        logger.error(f"[队列] 任务 #{task_id} 执行失败：{error}")
        next_item = self.start_next_waiting_task()
        self.task_queue_busy_changed.emit(self.has_incomplete_tasks())
        if next_item is None:
            refresh_request = _build_output_state_refresh_request(
                updated_payload,
                ExecutionTaskResult(completed_steps=(), summary=error, duration_seconds=0.0),
            )
            self.progress_display_requested.emit(
                QueueProgressUpdate(
                    status_text="状态：最近任务执行失败。",
                    note_text=f"当前进度：{progress_current}/{progress_total} · {updated_payload.error_message or error}",
                    progress_current=progress_current,
                    progress_total=progress_total,
                )
            )
            self.output_state_refresh_requested.emit(refresh_request)
        else:
            self.progress_display_requested.emit(QueueProgressUpdate())
        self.feedback_requested.emit(
            GuiNotice(title="任务执行失败", content=error, level="error")
        )

    def remove_task_item(self, item: QListWidgetItem) -> None:
        """从队列中移除指定任务项。"""
        payload = item.data(TASK_ITEM_ROLE)
        if not isinstance(payload, QueuedExecutionTask):
            return

        if payload.status == TASK_STATUS_RUNNING:
            self.feedback_requested.emit(
                GuiNotice(
                    title="暂不支持移除",
                    content="运行中的真实任务暂不支持直接移出队列，请等待任务结束后再处理。",
                    level="warning",
                )
            )
            return

        if not self._queue_panel.remove_task(item):
            return

        self.log_requested.emit(
            GuiLogMessage(level="info", message=f"[队列] 已移出任务：{payload.summary}")
        )
        self.task_queue_busy_changed.emit(self.has_incomplete_tasks())
        self.progress_display_requested.emit(QueueProgressUpdate())
        self.feedback_requested.emit(
            GuiNotice(
                title="已移出队列",
                content=payload.summary or item.text(),
                level="success",
            )
        )

    def clear_draft_queue(self) -> None:
        """清空当前任务队列中可直接移除的任务项。"""
        running_item = self.find_running_task_item()
        if running_item is not None:
            removed_count = self._queue_panel.clear_non_running_tasks()

            if removed_count == 0:
                self.log_requested.emit(
                    GuiLogMessage(
                        level="warning",
                        message="[队列] 当前存在运行中的任务，暂不支持直接清空。",
                    )
                )
                self.feedback_requested.emit(
                    GuiNotice(
                        title="暂无法清空",
                        content="运行中的真实任务暂不支持直接移出队列，请等待任务结束后再清空。",
                        level="warning",
                    )
                )
            else:
                self.log_requested.emit(
                    GuiLogMessage(
                        level="info",
                        message=f"[队列] 已清空 {removed_count} 条非运行中任务。",
                    )
                )
                self.task_queue_busy_changed.emit(self.has_incomplete_tasks())
                self.progress_display_requested.emit(QueueProgressUpdate())
            return

        self.clear_mock_queue()
        self.log_requested.emit(
            GuiLogMessage(level="info", message="[队列] 已清空当前任务队列。")
        )

    def fill_mock_queue(self, *, count: int) -> str:
        """填充指定数量的 mock 队列项。"""
        if count <= 0:
            raise ValueError("queue fill 需要大于 0 的整数参数。")

        self._queue_panel.clear_tasks()
        self._draft_count = count
        self._active_task_id = None
        self._active_worker = None
        self._stage_completion_notifications.clear()

        for task_id in range(1, count + 1):
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

            draft = ExecutionTaskDraft(
                source="dev_console",
                source_summary="开发控制台填充的 mock 队列",
            )
            summary = f"Mock任务 {task_id} · 列表调试"
            queued_task = QueuedExecutionTask(
                task_id=task_id,
                draft=draft,
                summary=summary,
                status=status,
                progress_current=progress_current,
                progress_total=progress_total,
                progress_message=progress_message,
            )
            self._queue_panel.append_task(
                queued_task,
                tooltip=self._build_task_item_tooltip(queued_task),
            )
            if status == TASK_STATUS_RUNNING and self._active_task_id is None:
                self._active_task_id = task_id

        self.task_running_changed.emit(self._active_task_id is not None)
        self.task_queue_busy_changed.emit(self.has_incomplete_tasks())
        self.progress_display_requested.emit(QueueProgressUpdate())
        return f"已填充 {count} 条 mock 队列项。"

    def clear_mock_queue(self) -> str:
        """清空当前调试队列并恢复占位状态。"""
        self._active_task_id = None
        self._active_worker = None
        self._stage_completion_notifications.clear()
        self.task_running_changed.emit(False)
        self.set_queue_placeholder()
        self.task_queue_busy_changed.emit(self.has_incomplete_tasks())
        self.progress_display_requested.emit(QueueProgressUpdate())
        return "已清空当前队列。"

    def shutdown(self) -> None:
        """清理执行中心后台任务引用。"""
        self._active_task_id = None
        self._active_worker = None
        self._stage_completion_notifications.clear()

    def inspect_queue(self, *, progress_card_height: int, builder_card_height: int) -> str:
        """返回当前队列列表与卡片尺寸信息。"""
        counts = self.queue_status_counts()
        row_height = self._queue_panel.draft_list.sizeHintForRow(0)
        return "\n".join(
            [
                f"queue_count={self.draft_queue_size()}",
                f"visible_rows={QUEUE_VISIBLE_ROW_COUNT}",
                f"row_height={row_height}",
                f"queue_height={self._queue_panel.draft_list.height()}",
                f"progress_card_height={progress_card_height}",
                f"builder_card_height={builder_card_height}",
                (
                    f"running={counts[TASK_STATUS_RUNNING]} "
                    f"waiting={counts[TASK_STATUS_WAITING]} "
                    f"completed={counts[TASK_STATUS_COMPLETED]}"
                ),
            ]
        )

    def set_queue_placeholder(self, text: str = "当前任务队列为空。") -> None:
        """为任务队列设置占位文本。"""
        self._queue_panel.set_placeholder(text)

    def apply_queue_list_height(self) -> None:
        """按默认可见行数收敛任务队列列表高度。"""
        self._queue_panel.apply_list_height()
