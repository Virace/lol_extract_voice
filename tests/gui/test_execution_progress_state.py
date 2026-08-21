"""验证执行队列到全局进度条的状态推导。"""

from __future__ import annotations

from datetime import datetime

from lol_audio_unpack.gui.components.global_progress_strip import GlobalProgressStripState
from lol_audio_unpack.gui.task_models import (
    TASK_STATUS_CANCELLED,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_PARTIAL,
    TASK_STATUS_RUNNING,
    TASK_STATUS_WAITING,
    AppContextInputSnapshot,
    ExecutionTaskDraft,
    ExecutionTaskParamsSnapshot,
    ExecutionTaskProgress,
    QueuedExecutionTask,
)
from lol_audio_unpack.gui.view.execution.progress_state import (
    build_global_progress_strip_state,
)

RUNNING_PROGRESS_VALUE = 2
RUNNING_PROGRESS_TOTAL = 5
TARGET_DIRECTORY_PROGRESS_CURRENT = 2
TARGET_DIRECTORY_PROGRESS_TOTAL = 6
FALLBACK_PROGRESS_CURRENT = 1
FALLBACK_PROGRESS_TOTAL = 3
TERMINAL_PROGRESS_TOTAL = 2


def _empty_counts() -> dict[str, int]:
    return {
        TASK_STATUS_RUNNING: 0,
        TASK_STATUS_WAITING: 0,
        TASK_STATUS_COMPLETED: 0,
        TASK_STATUS_FAILED: 0,
        TASK_STATUS_PARTIAL: 0,
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


def test_build_global_progress_strip_state_for_empty_queue() -> None:
    state = build_global_progress_strip_state(
        counts=_empty_counts(),
        running_task=None,
    )

    assert state == GlobalProgressStripState()


def test_build_global_progress_strip_state_preserves_terminal_summary_for_delayed_hide() -> None:
    """队列结束后的摘要应随隐藏请求传给宿主，而不是丢弃最终进度。"""
    state = build_global_progress_strip_state(
        counts=_empty_counts(),
        running_task=None,
        note_text="部分完成：成功 1，失败 1",
        progress_current=1,
        progress_total=2,
    )

    assert state.visible is False
    assert state.title_text == "任务已结束"
    assert state.detail_text == "部分完成：成功 1，失败 1"
    assert state.status_text == "1/2"
    assert state.progress_current == 1
    assert state.progress_total == TERMINAL_PROGRESS_TOTAL


def test_build_global_progress_strip_state_for_running_stage_progress() -> None:
    counts = _empty_counts()
    counts[TASK_STATUS_RUNNING] = 1
    running_task = _queued_task(
        status=TASK_STATUS_RUNNING,
        started_at=datetime(2026, 4, 5, 18, 0, 0),
        progress_detail=ExecutionTaskProgress(
            stage_key="extract",
            stage_label="音频解包",
            entity_scope_label="英雄",
            current=2,
            total=5,
            message="阿狸 解包完成",
        ),
    )

    state = build_global_progress_strip_state(
        counts=counts,
        running_task=running_task,
        now=datetime(2026, 4, 5, 18, 0, 8),
    )

    assert state.visible is True
    assert state.title_text == "音频解包 · 英雄"
    assert state.detail_text == "当前实体: 阿狸 (2/5)"
    assert state.rate_text == "均时 4.0s/实体"
    assert state.status_text == "运行中 · 2/5"
    assert state.progress_current == RUNNING_PROGRESS_VALUE
    assert state.progress_total == RUNNING_PROGRESS_TOTAL


def test_build_global_progress_strip_state_shows_wav_entity_and_running_index() -> None:
    counts = _empty_counts()
    counts[TASK_STATUS_RUNNING] = 1
    running_task = _queued_task(
        status=TASK_STATUS_RUNNING,
        started_at=datetime(2026, 4, 5, 18, 0, 0),
        progress_detail=ExecutionTaskProgress(
            stage_key="wav",
            stage_label="音频转码",
            entity_scope_label="英雄",
            current=TARGET_DIRECTORY_PROGRESS_CURRENT,
            total=TARGET_DIRECTORY_PROGRESS_TOTAL,
            message="正在处理: 阿狸",
        ),
    )

    state = build_global_progress_strip_state(
        counts=counts,
        running_task=running_task,
        now=datetime(2026, 4, 5, 18, 0, 8),
    )

    assert state.visible is True
    assert state.title_text == "音频转码 · 英雄"
    assert state.detail_text == "当前实体: 阿狸 (3/6)"
    assert state.rate_text == "均时 4.0s/实体"
    assert state.status_text == "运行中 · 3/6"
    assert state.progress_current == TARGET_DIRECTORY_PROGRESS_CURRENT
    assert state.progress_total == TARGET_DIRECTORY_PROGRESS_TOTAL


def test_build_global_progress_strip_state_uses_task_progress_without_structured_detail() -> None:
    """调试或旧调用方只有任务级进度时，也应展示真实进度而非回退为零。"""
    counts = _empty_counts()
    counts[TASK_STATUS_RUNNING] = 1
    running_task = _queued_task(
        status=TASK_STATUS_RUNNING,
        progress_current=FALLBACK_PROGRESS_CURRENT,
        progress_total=FALLBACK_PROGRESS_TOTAL,
        progress_message="模拟队列运行中",
    )

    state = build_global_progress_strip_state(
        counts=counts,
        running_task=running_task,
    )

    assert state.title_text == "当前阶段"
    assert state.detail_text == "当前进度"
    assert state.status_text == "当前阶段 · 1/3"
    assert state.progress_current == FALLBACK_PROGRESS_CURRENT
    assert state.progress_total == FALLBACK_PROGRESS_TOTAL


def test_build_global_progress_strip_state_waiting_task_keeps_simple_preparing_text() -> None:
    counts = _empty_counts()
    counts[TASK_STATUS_WAITING] = 1

    state = build_global_progress_strip_state(
        counts=counts,
        running_task=None,
        note_text="状态：任务已创建。",
    )

    assert state.visible is True
    assert state.title_text == "准备启动"
    assert state.detail_text == "准备中"
    assert state.rate_text == ""
    assert state.status_text == "状态：任务已创建。"
