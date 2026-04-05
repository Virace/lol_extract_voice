"""执行中心全局进度条所需的状态推导。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

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


ENTITY_COMPLETION_PATTERNS = {
    "extract": re.compile(r"^(?P<label>.+?) 解包(?:完成|失败)$"),
    "mapping": re.compile(r"^(?P<label>.+?) 映射(?:完成|失败)$"),
}
WAV_RUNNING_PATTERN = re.compile(r"^正在处理: (?P<label>.+)$")
WAV_FINISHED_PATTERN = re.compile(r"^WAV 转码目录完成：(?P<label>.+)$")


@dataclass(slots=True, frozen=True)
class _RunningEntitySnapshot:
    """描述当前进度快照中可展示的实体信息。"""

    label: str
    display_index: int | None


def _clamp_progress_index(value: int, total: int) -> int | None:
    """将进度索引限制在合法范围内。"""
    if total <= 0:
        return None
    if value <= 0:
        return 1
    return min(value, total)


def _resolve_running_entity_snapshot(running_progress: ExecutionTaskProgress) -> _RunningEntitySnapshot:
    """根据结构化进度解析当前应展示的实体标签与序号。"""
    message = running_progress.message.strip()
    total = running_progress.total

    if running_progress.stage_key == "wav":
        running_match = WAV_RUNNING_PATTERN.fullmatch(message)
        if running_match is not None:
            return _RunningEntitySnapshot(
                label=running_match.group("label"),
                display_index=_clamp_progress_index(running_progress.current + 1, total),
            )

        finished_match = WAV_FINISHED_PATTERN.fullmatch(message)
        if finished_match is not None:
            return _RunningEntitySnapshot(
                label=finished_match.group("label"),
                display_index=_clamp_progress_index(running_progress.current, total),
            )

    completion_pattern = ENTITY_COMPLETION_PATTERNS.get(running_progress.stage_key)
    if completion_pattern is not None:
        completion_match = completion_pattern.fullmatch(message)
        if completion_match is not None:
            return _RunningEntitySnapshot(
                label=completion_match.group("label"),
                display_index=_clamp_progress_index(running_progress.current, total),
            )

    if message:
        return _RunningEntitySnapshot(
            label=message,
            display_index=_clamp_progress_index(running_progress.current, total),
        )

    return _RunningEntitySnapshot(label="", display_index=None)


def _build_stage_title_text(running_progress: ExecutionTaskProgress | None) -> tuple[str, str]:
    """构造左侧标题区的上下两行文本。"""
    if running_progress is None:
        return "准备启动", "准备中"

    title_parts = [running_progress.stage_label]
    if running_progress.entity_scope_label:
        title_parts.append(running_progress.entity_scope_label)

    entity_snapshot = _resolve_running_entity_snapshot(running_progress)
    if entity_snapshot.label and entity_snapshot.display_index is not None and running_progress.total > 0:
        detail_text = f"当前实体: {entity_snapshot.label} ({entity_snapshot.display_index}/{running_progress.total})"
    elif entity_snapshot.label:
        detail_text = f"当前实体: {entity_snapshot.label}"
    else:
        detail_text = "当前实体: 准备中"

    return " · ".join(title_parts), detail_text


def _build_progress_panel_note_text(running_progress: ExecutionTaskProgress | None) -> str:
    """构造执行页进度摘要中的说明文本。"""
    if running_progress is None:
        return "当前阶段 · 准备中"

    entity_snapshot = _resolve_running_entity_snapshot(running_progress)
    if entity_snapshot.label and entity_snapshot.display_index is not None and running_progress.total > 0:
        return f"当前实体：{entity_snapshot.label} ({entity_snapshot.display_index}/{running_progress.total})"
    if entity_snapshot.label:
        return f"当前实体：{entity_snapshot.label}"
    return "当前实体：准备中"


def _build_global_strip_status_text(running_progress: ExecutionTaskProgress | None, fallback_note: str | None) -> str:
    """构造底部全局进度条右侧的单行状态文案。"""
    if running_progress is None:
        return fallback_note or ""

    entity_snapshot = _resolve_running_entity_snapshot(running_progress)
    if entity_snapshot.display_index is not None and running_progress.total > 0:
        status_prefix = "已完成" if running_progress.stage_finished else "运行中"
        return f"{status_prefix} · {entity_snapshot.display_index}/{running_progress.total}"
    if running_progress.message.strip():
        return running_progress.message.strip()
    return "准备中"

def _build_global_strip_rate_text(
    running_task: QueuedExecutionTask | None,
    running_progress: ExecutionTaskProgress | None,
    *,
    now: datetime | None,
) -> str:
    """构造底部全局进度条右上角的节奏指标。"""
    if (
        not isinstance(running_task, QueuedExecutionTask)
        or running_progress is None
        or running_task.started_at is None
    ):
        return ""

    reference_now = now or datetime.now()
    elapsed_seconds = max((reference_now - running_task.started_at).total_seconds(), 0.0)
    completed_count = max(running_progress.current, 0)
    if completed_count > 0:
        return f"均时 {elapsed_seconds / completed_count:.1f}s/实体"
    if elapsed_seconds > 0:
        return f"已运行 {elapsed_seconds:.1f}s"
    return ""


def build_global_progress_strip_state(  # noqa: PLR0913
    *,
    draft_count: int,
    counts: dict[str, int],
    running_task: QueuedExecutionTask | None,
    status_text: str | None = None,
    note_text: str | None = None,
    progress_current: int | None = None,
    progress_total: int | None = None,
    now: datetime | None = None,
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
            title_text, detail_text = _build_stage_title_text(running_progress)
        elif running_progress is not None:
            title_text, detail_text = _build_stage_title_text(running_progress)
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
        rate_text=_build_global_strip_rate_text(running_task, running_progress, now=now),
        status_text=_build_global_strip_status_text(running_progress, note_text),
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
            title_text, _ = _build_stage_title_text(running_progress)
            status_text = f"当前阶段：{title_text}"
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
                note_text = _build_progress_panel_note_text(running_progress)
            elif running_progress is not None:
                note_text = _build_progress_panel_note_text(running_progress)
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
