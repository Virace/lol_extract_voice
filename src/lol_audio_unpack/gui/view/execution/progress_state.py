"""执行中心全局进度条所需的状态推导。"""

from __future__ import annotations

from dataclasses import dataclass

from lol_audio_unpack.gui.components.global_progress_strip import GlobalProgressStripState
from lol_audio_unpack.gui.task_models import (
    TASK_STATUS_CANCELLED,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_RUNNING,
    TASK_STATUS_WAITING,
    ExecutionTaskProgress,
    QueuedExecutionTask,
)


@dataclass(slots=True, frozen=True)
class ProgressDisplayState:
    """描述执行中心当前应展示的进度摘要。"""

    status_text: str
    note_text: str
    progress_value: int
    progress_total: int
    queue_summary_text: str


def build_global_progress_strip_state(  # noqa: PLR0913
    *,
    draft_count: int,
    counts: dict[str, int],
    running_task: QueuedExecutionTask | None,
    status_text: str | None = None,
    note_text: str | None = None,
    progress_current: int | None = None,
    progress_total: int | None = None,
) -> GlobalProgressStripState:
    """根据当前队列状态构造底部全局进度条展示快照。"""
    has_visible_task = counts[TASK_STATUS_RUNNING] > 0 or counts[TASK_STATUS_WAITING] > 0
    if not has_visible_task:
        return GlobalProgressStripState()

    running_progress = (
        running_task.progress_detail
        if isinstance(running_task, QueuedExecutionTask)
        and isinstance(running_task.progress_detail, ExecutionTaskProgress)
        else None
    )

    if isinstance(running_task, QueuedExecutionTask):
        if running_progress is not None and running_progress.total > 0:
            title_text = running_progress.stage_label
            detail_text = running_progress.entity_scope_label or "当前进度"
        elif running_progress is not None:
            title_text = running_progress.stage_label
            detail_text = running_progress.entity_scope_label or "准备中"
        elif progress_total is not None and progress_total > 0 and progress_current is not None:
            title_text = "当前阶段"
            detail_text = "当前进度"
        else:
            title_text = "准备启动"
            detail_text = "准备中"
    else:
        title_text = "准备启动"
        detail_text = "准备中"

    return GlobalProgressStripState(
        visible=True,
        title_text=title_text,
        detail_text=detail_text,
        progress_current=max(progress_current or (running_progress.current if running_progress is not None else 0), 0),
        progress_total=max(progress_total or (running_progress.total if running_progress is not None else 1), 1),
        rate_text=(
            f"{running_progress.current}/{running_progress.total}"
            if running_progress is not None and running_progress.total > 0
            else (
                f"{progress_current}/{progress_total}"
                if progress_current is not None and progress_total is not None and progress_total > 0
                else ""
            )
        ),
        status_text=running_progress.message if running_progress is not None else (note_text or ""),
    )


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
    """根据当前队列状态构造进度展示快照。"""
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
                note_text = f"{running_progress.stage_label} · {progress_value}/{progress_bar_total}"
            elif running_progress is not None:
                note_text = f"{running_progress.stage_label} · 准备中"
            elif running_task.progress_total > 0:
                note_text = f"当前阶段 · {progress_value}/{progress_bar_total}"
            else:
                note_text = "当前阶段 · 准备中"
        elif draft_count == 0:
            note_text = "等待创建第一条任务。"
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
