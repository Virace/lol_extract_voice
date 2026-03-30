"""执行中心队列状态机控制器测试。"""

from __future__ import annotations

from lol_audio_unpack.gui.controllers.execution_queue_controller import ExecutionQueueController
from lol_audio_unpack.gui.task_models import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_RUNNING,
    ExecutionTaskDraft,
    ExecutionTaskParamsSnapshot,
    ExecutionTaskResult,
    OutputStateRefreshRequest,
)
from lol_audio_unpack.gui.view.execution.task_queue_panel import TASK_ITEM_ROLE, TaskQueuePanel


def _build_controller(qtbot) -> tuple[ExecutionQueueController, TaskQueuePanel]:
    panel = TaskQueuePanel()
    qtbot.addWidget(panel)
    controller = ExecutionQueueController(
        queue_panel=panel,
        build_task_item_tooltip=lambda task: f"task:{task.task_id}",
        parent=panel,
    )
    return controller, panel


def test_execution_queue_controller_enqueue_task_starts_first_waiting_task(qtbot, monkeypatch) -> None:
    controller, panel = _build_controller(qtbot)
    started_tasks = []

    def _capture_started_task(task) -> None:
        started_tasks.append(task)

    monkeypatch.setattr(controller, "start_task_worker", _capture_started_task)

    queued_task = controller.enqueue_task(
        draft=ExecutionTaskDraft(source="manual_input", source_summary="手动输入"),
        summary="测试任务",
    )

    assert panel.task_count() == 1
    running_item = panel.find_running_task_item()
    assert running_item is not None
    running_payload = running_item.data(TASK_ITEM_ROLE)
    assert running_payload.task_id == queued_task.task_id
    assert running_payload.status == TASK_STATUS_RUNNING
    assert controller.active_task_id == queued_task.task_id
    assert started_tasks == [running_payload]


def test_execution_queue_controller_on_task_finished_emits_refresh_request_for_last_task(
    qtbot,
    monkeypatch,
) -> None:
    controller, panel = _build_controller(qtbot)

    def _ignore_started_task(_task) -> None:
        return None

    monkeypatch.setattr(controller, "start_task_worker", _ignore_started_task)
    refresh_requests = []
    controller.output_state_refresh_requested.connect(refresh_requests.append)

    queued_task = controller.enqueue_task(
        draft=ExecutionTaskDraft(
            source="manual_input",
            source_summary="手动输入",
            task_params=ExecutionTaskParamsSnapshot(champion_ids=(1, 103)),
        ),
        summary="测试任务",
    )

    controller.on_task_finished(
        queued_task.task_id,
        ExecutionTaskResult(
            completed_steps=("音频解包",),
            summary="执行完成",
            duration_seconds=1.2,
        ),
    )

    completed_item = panel.find_task_item_by_id(queued_task.task_id)
    assert completed_item is not None
    completed_payload = completed_item.data(TASK_ITEM_ROLE)
    assert completed_payload.status == TASK_STATUS_COMPLETED
    assert controller.active_task_id is None
    assert refresh_requests == [OutputStateRefreshRequest(champion_ids=("1", "103"))]
