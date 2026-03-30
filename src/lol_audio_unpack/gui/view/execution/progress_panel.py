"""执行中心的任务进度面板。"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, CardWidget, ProgressBar, StrongBodyLabel

from lol_audio_unpack.gui.task_models import (
    TASK_STATUS_CANCELLED,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_RUNNING,
    TASK_STATUS_WAITING,
    ExecutionTaskProgress,
    QueuedExecutionTask,
)
from lol_audio_unpack.gui.view.execution.task_queue_panel import TaskQueuePanel


@dataclass(slots=True, frozen=True)
class ProgressDisplayState:
    """描述任务进度面板当前应展示的状态。"""

    status_text: str
    note_text: str
    progress_value: int
    progress_total: int
    queue_summary_text: str


def build_progress_display_state(  # noqa: PLR0913
    *,
    draft_count: int,
    counts: dict[str, int],
    running_task: QueuedExecutionTask | None,
    status_text: str | None = None,
    note_text: str | None = None,
    progress_current: int | None = None,
    progress_total: int | None = None,
) -> ProgressDisplayState:
    """根据当前队列状态构造面板展示快照。"""
    progress_bar_total = max(progress_total, 1) if progress_total is not None else 1
    progress_value = min(max(progress_current or 0, 0), progress_bar_total)
    running_progress = (
        running_task.progress_detail
        if isinstance(running_task, QueuedExecutionTask)
        and isinstance(running_task.progress_detail, ExecutionTaskProgress)
        else None
    )

    if progress_current is None and progress_total is None and isinstance(running_task, QueuedExecutionTask):
        if running_progress is not None and running_progress.total > 0:
            progress_bar_total = max(running_progress.total, 1)
            progress_value = min(max(running_progress.current, 0), progress_bar_total)
        elif running_task.progress_total > 0:
            progress_bar_total = max(running_task.progress_total, 1)
            progress_value = min(max(running_task.progress_current, 0), progress_bar_total)
        else:
            progress_bar_total = 1
            progress_value = 0

    if status_text is None:
        if draft_count == 0:
            status_text = "状态：界面已就绪，等待创建第一条任务。"
        elif isinstance(running_task, QueuedExecutionTask) and running_progress is not None:
            stage_text = f"当前阶段：{running_progress.stage_label}"
            if running_progress.entity_scope_label:
                stage_text = f"{stage_text} · {running_progress.entity_scope_label}"
            status_text = stage_text
        elif isinstance(running_task, QueuedExecutionTask):
            status_text = "状态：队列中有运行中的任务。"
        elif counts[TASK_STATUS_WAITING] > 0:
            status_text = "状态：队列中有等待中的任务。"
        elif counts[TASK_STATUS_FAILED] > 0:
            status_text = "状态：队列中存在执行失败的任务。"
        elif counts[TASK_STATUS_COMPLETED] > 0:
            status_text = "状态：队列中的任务已执行完成。"
        else:
            status_text = "状态：当前队列中的任务已取消。"

    if note_text is None:
        if isinstance(running_task, QueuedExecutionTask):
            if running_progress is not None and running_progress.total > 0:
                stage_summary = running_progress.stage_label
                if running_progress.entity_scope_label:
                    stage_summary = f"{stage_summary} · {running_progress.entity_scope_label}"
                note_text = (
                    f"{stage_summary} · {progress_value}/{progress_bar_total} · "
                    f"{running_progress.message or '后台任务执行中。'}"
                )
            elif running_progress is not None:
                stage_summary = running_progress.stage_label
                if running_progress.entity_scope_label:
                    stage_summary = f"{stage_summary} · {running_progress.entity_scope_label}"
                note_text = f"{stage_summary} · 准备中 · {running_progress.message or '后台任务执行中。'}"
            elif running_task.progress_total > 0:
                note_text = (
                    f"当前进度：{progress_value}/{progress_bar_total} · "
                    f"{running_task.progress_message or '后台任务执行中。'}"
                )
            else:
                note_text = f"准备中 · {running_task.progress_message or '后台任务执行中。'}"
        elif draft_count == 0:
            note_text = "界面已就绪，等待创建第一条任务。"
        elif counts[TASK_STATUS_COMPLETED] > 0 and counts[TASK_STATUS_RUNNING] == 0 and counts[TASK_STATUS_WAITING] == 0:
            progress_bar_total = 100
            progress_value = 100
            note_text = "100% · 队列中的可执行任务已完成。"
        elif counts[TASK_STATUS_FAILED] > 0 and counts[TASK_STATUS_RUNNING] == 0:
            note_text = "执行失败，请查看日志抽屉和错误提示定位失败原因。"
        else:
            note_text = "当前显示任务队列状态。"

    queue_summary_text = (
        "任务队列："
        f"{draft_count} 条 · 运行中 {counts[TASK_STATUS_RUNNING]} · 等待中 {counts[TASK_STATUS_WAITING]} "
        f"· 已完成 {counts[TASK_STATUS_COMPLETED]} · 失败 {counts[TASK_STATUS_FAILED]} · 已取消 {counts[TASK_STATUS_CANCELLED]}"
    )
    return ProgressDisplayState(
        status_text=status_text,
        note_text=note_text,
        progress_value=progress_value,
        progress_total=progress_bar_total,
        queue_summary_text=queue_summary_text,
    )


class ProgressPanel(CardWidget):
    """承载执行状态摘要与任务队列展示。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化任务进度面板。

        Args:
            parent: 父级控件。
        """
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        progress_title = StrongBodyLabel("任务进度", self)
        self.task_status_label = CaptionLabel("状态：界面已就绪，等待创建第一条任务。", self)
        self.task_status_label.hide()
        self.task_progress_bar = ProgressBar(self)
        self.task_progress_bar.setRange(0, 1)
        self.task_progress_bar.setValue(0)
        self.task_progress_note = StrongBodyLabel("当前进度：暂无运行中的任务。", self)
        self.queue_progress_label = CaptionLabel("任务队列：0 条", self)
        self.queue_panel = TaskQueuePanel(self)

        layout.addWidget(progress_title)
        layout.addWidget(self.task_progress_bar)
        layout.addWidget(self.task_progress_note)
        layout.addWidget(self.queue_progress_label)
        layout.addWidget(self.queue_panel)

    @property
    def draft_list(self):
        """返回队列列表控件。"""
        return self.queue_panel.draft_list

    def set_queue_placeholder(self, text: str) -> None:
        """设置空队列占位文案。"""
        self.queue_panel.set_placeholder(text)

    def apply_queue_list_height(self) -> None:
        """同步任务队列列表高度。"""
        self.queue_panel.apply_list_height()

    def apply_display_state(self, state: ProgressDisplayState) -> None:
        """将展示快照应用到进度面板控件。"""
        self.task_progress_bar.setRange(0, state.progress_total)
        self.task_progress_bar.setValue(state.progress_value)
        self.task_status_label.setText(state.status_text)
        self.task_progress_note.setText(state.note_text)
        self.queue_progress_label.setText(state.queue_summary_text)
