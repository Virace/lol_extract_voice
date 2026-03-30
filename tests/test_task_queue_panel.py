"""执行中心任务队列面板测试。"""

from __future__ import annotations

from lol_audio_unpack.gui.task_models import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_RUNNING,
    ExecutionTaskDraft,
    QueuedExecutionTask,
)
from lol_audio_unpack.gui.view.execution.task_queue_panel import (
    TASK_ITEM_ROLE,
    TaskQueueContextMenuState,
    TaskQueuePanel,
    build_task_queue_context_menu_state,
)


def _task(*, status: str) -> QueuedExecutionTask:
    return QueuedExecutionTask(
        task_id=1,
        draft=ExecutionTaskDraft(source="test", source_summary="summary"),
        summary="测试任务",
        status=status,
    )


def test_build_task_queue_context_menu_state_for_running_task() -> None:
    state = build_task_queue_context_menu_state(
        payload=_task(status=TASK_STATUS_RUNNING),
        has_real_tasks=True,
        has_running_task=True,
        has_removable_tasks=True,
    )

    assert state == TaskQueueContextMenuState(
        remove_text="运行中的任务暂不支持移除",
        remove_enabled=False,
        show_clear=True,
        clear_text="清空全部非运行中任务",
    )


def test_build_task_queue_context_menu_state_for_completed_task() -> None:
    state = build_task_queue_context_menu_state(
        payload=_task(status=TASK_STATUS_COMPLETED),
        has_real_tasks=True,
        has_running_task=False,
        has_removable_tasks=True,
    )

    assert state == TaskQueueContextMenuState(
        remove_text="删除该任务",
        remove_enabled=True,
        show_clear=True,
        clear_text="清空全部队列",
    )


def test_build_task_queue_context_menu_state_for_empty_queue() -> None:
    state = build_task_queue_context_menu_state(
        payload=None,
        has_real_tasks=False,
        has_running_task=False,
        has_removable_tasks=False,
    )

    assert state is None


def test_task_queue_panel_tracks_real_tasks_and_running_item(qtbot) -> None:
    panel = TaskQueuePanel()
    qtbot.addWidget(panel)

    waiting_task = QueuedExecutionTask(
        task_id=1,
        draft=ExecutionTaskDraft(source="test", source_summary="summary"),
        summary="等待任务",
    )
    running_task = QueuedExecutionTask(
        task_id=2,
        draft=ExecutionTaskDraft(source="test", source_summary="summary"),
        summary="运行任务",
        status=TASK_STATUS_RUNNING,
    )

    panel.set_placeholder("当前任务队列为空。")
    panel.append_task(waiting_task, tooltip="waiting")
    panel.append_task(running_task, tooltip="running")

    assert panel.task_count() == len((waiting_task, running_task))
    assert panel.find_task_item_by_id(1) is not None
    running_item = panel.find_running_task_item()
    assert running_item is not None
    assert running_item.data(TASK_ITEM_ROLE) == running_task
