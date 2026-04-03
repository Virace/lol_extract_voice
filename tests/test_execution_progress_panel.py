from __future__ import annotations

from lol_audio_unpack.gui.components.global_progress_strip import GlobalProgressStripState
from lol_audio_unpack.gui.task_models import (
    TASK_STATUS_CANCELLED,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_RUNNING,
    TASK_STATUS_WAITING,
    AppContextInputSnapshot,
    ExecutionTaskDraft,
    ExecutionTaskParamsSnapshot,
    ExecutionTaskProgress,
    QueuedExecutionTask,
)
from lol_audio_unpack.gui.view.execution.progress_state import (
    ProgressDisplayState,
    build_global_progress_strip_state,
    build_progress_display_state,
)

RUNNING_PROGRESS_VALUE = 2
RUNNING_PROGRESS_TOTAL = 5
COMPLETED_PROGRESS_PERCENT = 100


def _empty_counts() -> dict[str, int]:
    return {
        TASK_STATUS_RUNNING: 0,
        TASK_STATUS_WAITING: 0,
        TASK_STATUS_COMPLETED: 0,
        TASK_STATUS_FAILED: 0,
        TASK_STATUS_CANCELLED: 0,
    }


def _queued_task(**kwargs) -> QueuedExecutionTask:
    draft = ExecutionTaskDraft(
        source="default_scope",
        source_summary="全部英雄+地图",
        context_input=AppContextInputSnapshot(),
        task_params=ExecutionTaskParamsSnapshot(),
    )
    return QueuedExecutionTask(task_id=1, draft=draft, summary="测试任务", **kwargs)


def test_build_progress_display_state_for_empty_queue() -> None:
    state = build_progress_display_state(
        draft_count=0,
        counts=_empty_counts(),
        running_task=None,
    )

    assert state == ProgressDisplayState(
        status_text="状态：界面已就绪，等待创建第一条任务。",
        note_text="等待创建第一条任务。",
        progress_value=0,
        progress_total=1,
        queue_summary_text="任务队列：0 条 · 运行中 0 · 等待中 0 · 已完成 0 · 失败 0 · 已取消 0",
    )


def test_build_progress_display_state_for_running_stage_progress() -> None:
    counts = _empty_counts()
    counts[TASK_STATUS_RUNNING] = 1
    running_task = _queued_task(
        status=TASK_STATUS_RUNNING,
        progress_detail=ExecutionTaskProgress(
            stage_key="extract",
            stage_label="音频解包",
            entity_scope_label="英雄",
            current=2,
            total=5,
            message="处理中",
        ),
    )

    state = build_progress_display_state(
        draft_count=1,
        counts=counts,
        running_task=running_task,
    )

    assert state.status_text == "当前阶段：音频解包 · 英雄"
    assert state.note_text == "音频解包 · 2/5"
    assert state.progress_value == RUNNING_PROGRESS_VALUE
    assert state.progress_total == RUNNING_PROGRESS_TOTAL


def test_build_progress_display_state_for_all_completed_queue() -> None:
    counts = _empty_counts()
    counts[TASK_STATUS_COMPLETED] = 2

    state = build_progress_display_state(
        draft_count=2,
        counts=counts,
        running_task=None,
    )

    assert state.status_text == "状态：队列中的任务已执行完成。"
    assert state.note_text == "100% · 队列中的可执行任务已完成。"
    assert state.progress_value == COMPLETED_PROGRESS_PERCENT
    assert state.progress_total == COMPLETED_PROGRESS_PERCENT


def test_build_global_progress_strip_state_for_empty_queue() -> None:
    state = build_global_progress_strip_state(
        draft_count=0,
        counts=_empty_counts(),
        running_task=None,
    )

    assert state == GlobalProgressStripState()


def test_build_global_progress_strip_state_for_running_stage_progress() -> None:
    counts = _empty_counts()
    counts[TASK_STATUS_RUNNING] = 1
    running_task = _queued_task(
        status=TASK_STATUS_RUNNING,
        progress_detail=ExecutionTaskProgress(
            stage_key="extract",
            stage_label="音频解包",
            entity_scope_label="英雄",
            current=2,
            total=5,
            message="处理中",
        ),
    )

    state = build_global_progress_strip_state(
        draft_count=1,
        counts=counts,
        running_task=running_task,
    )

    assert state.visible is True
    assert state.title_text == "音频解包"
    assert state.detail_text == "英雄"
    assert state.rate_text == "2/5"
    assert state.status_text == "处理中"
    assert state.progress_current == RUNNING_PROGRESS_VALUE
    assert state.progress_total == RUNNING_PROGRESS_TOTAL


def test_build_global_progress_strip_state_waiting_task_keeps_simple_preparing_text() -> None:
    counts = _empty_counts()
    counts[TASK_STATUS_WAITING] = 1

    state = build_global_progress_strip_state(
        draft_count=1,
        counts=counts,
        running_task=None,
    )

    assert state.visible is True
    assert state.title_text == "准备启动"
    assert state.detail_text == "准备中"
    assert state.rate_text == ""
    assert state.status_text == ""
