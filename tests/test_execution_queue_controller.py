"""执行中心队列状态机控制器测试。"""

from __future__ import annotations

from types import SimpleNamespace

import lol_audio_unpack.gui.controllers.execution_queue_controller as queue_module
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


def test_execution_queue_controller_on_task_started_logs_info(qtbot, monkeypatch) -> None:
    controller, _panel = _build_controller(qtbot)
    info_messages: list[str] = []

    monkeypatch.setattr(
        queue_module,
        "logger",
        SimpleNamespace(info=lambda message: info_messages.append(str(message))),
    )
    monkeypatch.setattr(controller, "start_task_worker", lambda _task: None)

    queued_task = controller.enqueue_task(
        draft=ExecutionTaskDraft(source="manual_input", source_summary="手动输入"),
        summary="测试任务",
    )

    controller.on_task_started(queued_task.task_id)

    assert info_messages == [f"[队列] 任务 #{queued_task.task_id} 已开始执行"]


def test_execution_queue_controller_on_task_finished_logs_success(qtbot, monkeypatch) -> None:
    controller, _panel = _build_controller(qtbot)
    success_messages: list[str] = []

    monkeypatch.setattr(
        queue_module,
        "logger",
        SimpleNamespace(success=lambda message: success_messages.append(str(message))),
    )
    monkeypatch.setattr(controller, "start_task_worker", lambda _task: None)

    queued_task = controller.enqueue_task(
        draft=ExecutionTaskDraft(source="manual_input", source_summary="手动输入"),
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

    assert success_messages == [f"[队列] 任务 #{queued_task.task_id} 执行完成：执行完成"]


def test_execution_queue_controller_shutdown_clears_active_state(qtbot) -> None:
    controller, _panel = _build_controller(qtbot)
    controller._active_task_id = 1
    controller._active_worker = object()

    assert controller.has_active_background_work() is True

    controller.shutdown()

    assert controller.has_active_background_work() is False
    assert controller.active_task_id is None
