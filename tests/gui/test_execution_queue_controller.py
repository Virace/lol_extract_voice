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


def _build_controller() -> ExecutionQueueController:
    return ExecutionQueueController(
        build_task_item_tooltip=lambda task: f"task:{task.task_id}",
    )


def test_execution_queue_controller_enqueue_task_starts_first_waiting_task(monkeypatch) -> None:
    controller = _build_controller()
    started_tasks = []

    def _capture_started_task(task) -> None:
        started_tasks.append(task)

    monkeypatch.setattr(controller, "start_task_worker", _capture_started_task)

    queued_task = controller.enqueue_task(
        draft=ExecutionTaskDraft(source="manual_input", source_summary="手动输入"),
        summary="测试任务",
    )

    assert controller.draft_queue_size() == 1
    running_payload = controller.find_running_task()
    assert running_payload is not None
    assert running_payload.task_id == queued_task.task_id
    assert running_payload.status == TASK_STATUS_RUNNING
    assert controller.active_task_id == queued_task.task_id
    assert started_tasks == [running_payload]


def test_execution_queue_controller_on_task_finished_emits_refresh_request_for_last_task(
    monkeypatch,
) -> None:
    controller = _build_controller()

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

    completed_payload = controller.find_task_by_id(queued_task.task_id)
    assert completed_payload is not None
    assert completed_payload.status == TASK_STATUS_COMPLETED
    assert controller.active_task_id is None
    assert refresh_requests == [OutputStateRefreshRequest(champion_ids=("1", "103"))]


def test_execution_queue_controller_on_task_started_logs_info(monkeypatch) -> None:
    controller = _build_controller()
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


def test_execution_queue_controller_on_task_finished_logs_success(monkeypatch) -> None:
    controller = _build_controller()
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


def test_execution_queue_controller_shutdown_clears_active_state() -> None:
    controller = _build_controller()
    controller._active_task_id = 1
    controller._active_worker = object()

    assert controller.has_active_background_work() is True

    controller.shutdown()

    assert controller.has_active_background_work() is False
    assert controller.active_task_id is None


def test_execution_queue_controller_tracks_background_wav_process_after_task_finished(monkeypatch) -> None:
    controller = _build_controller()
    feedbacks = []
    controller.feedback_requested.connect(feedbacks.append)
    monkeypatch.setattr(controller, "start_task_worker", lambda _task: None)

    class FakeProcess:
        def __init__(self) -> None:
            self.returncode = None

        def poll(self) -> int | None:
            return self.returncode

        def terminate(self) -> None:
            self.returncode = 1

    queued_task = controller.enqueue_task(
        draft=ExecutionTaskDraft(source="manual_input", source_summary="手动输入"),
        summary="测试任务",
    )
    process = FakeProcess()

    controller.on_task_finished(
        queued_task.task_id,
        ExecutionTaskResult(
            completed_steps=("音频解包", "事件映射"),
            summary="执行完成；WAV 转码仍在后台继续",
            duration_seconds=1.2,
            wav_background_process=process,
            wav_background_notice="任务 #1 的事件映射已完成，WAV 转码仍在后台继续。",
        ),
    )

    assert controller.has_active_background_work() is True
    assert feedbacks[-1].title == "WAV 转码后台继续"
    assert feedbacks[-1].content == "任务 #1 的事件映射已完成，WAV 转码仍在后台继续。"

    process.returncode = 0

    assert controller.has_active_background_work() is False


def test_execution_queue_controller_shutdown_terminates_background_wav_processes() -> None:
    controller = _build_controller()

    class FakeProcess:
        def __init__(self) -> None:
            self.returncode = None
            self.terminated = False

        def poll(self) -> int | None:
            return self.returncode

        def terminate(self) -> None:
            self.terminated = True
            self.returncode = 1

    process = FakeProcess()
    controller._background_wav_processes = {1: process}

    controller.shutdown()

    assert process.terminated is True
    assert controller.has_active_background_work() is False
