"""执行中心队列状态机控制器测试。"""

from __future__ import annotations

from types import SimpleNamespace

import lol_audio_unpack.gui.controllers.execution_queue as queue_module
from lol_audio_unpack.gui.controllers.execution_queue import ExecutionQueueController
from lol_audio_unpack.gui.task_models import (
    TASK_STATUS_CANCELLED,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_RUNNING,
    ExecutionTaskDraft,
    ExecutionTaskParamsSnapshot,
    ExecutionTaskResult,
    OutputStateRefreshRequest,
)


class _FakeExecutionThread:
    """模拟可被强制终止的执行线程。"""

    def __init__(self, *, wait_result: bool = False) -> None:
        self.calls: list[object] = []
        self._wait_result = wait_result
        self._running = True

    def isRunning(self) -> bool:  # noqa: N802
        """返回线程当前是否仍在运行。"""
        return self._running

    def requestInterruption(self) -> None:  # noqa: N802
        """记录中断请求。"""
        self.calls.append("requestInterruption")

    def quit(self) -> None:
        """记录退出请求。"""
        self.calls.append("quit")

    def wait(self, timeout_ms: int) -> bool:
        """记录等待调用，并按预设结果返回。"""
        self.calls.append(("wait", timeout_ms))
        if self._wait_result:
            self._running = False
        return self._wait_result

    def terminate(self) -> None:
        """记录强制终止调用。"""
        self.calls.append("terminate")
        self._running = False


def _build_controller(*, single_task_mode: bool = False) -> ExecutionQueueController:
    return ExecutionQueueController(
        build_task_item_tooltip=lambda task: f"task:{task.task_id}",
        single_task_mode=single_task_mode,
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


def test_execution_queue_controller_single_task_mode_absorbs_duplicate_enqueue(monkeypatch) -> None:
    controller = _build_controller(single_task_mode=True)
    started_tasks = []

    def _capture_started_task(task) -> None:
        started_tasks.append(task)

    monkeypatch.setattr(controller, "start_task_worker", _capture_started_task)

    first_task = controller.enqueue_task(
        draft=ExecutionTaskDraft(source="manual_input", source_summary="手动输入"),
        summary="测试任务",
    )
    second_task = controller.enqueue_task(
        draft=ExecutionTaskDraft(source="manual_input", source_summary="手动输入"),
        summary="重复触发任务",
    )

    assert first_task.task_id == second_task.task_id
    assert controller.draft_queue_size() == 1
    assert controller.active_task_id == first_task.task_id
    assert started_tasks == [controller.find_running_task()]


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


def test_execution_queue_controller_single_task_mode_clears_stale_history_before_next_task(
    monkeypatch,
) -> None:
    controller = _build_controller(single_task_mode=True)

    monkeypatch.setattr(controller, "start_task_worker", lambda _task: None)

    first_task = controller.enqueue_task(
        draft=ExecutionTaskDraft(source="manual_input", source_summary="手动输入"),
        summary="第一次任务",
    )
    controller.on_task_finished(
        first_task.task_id,
        ExecutionTaskResult(
            completed_steps=("音频解包",),
            summary="执行完成",
            duration_seconds=1.2,
        ),
    )

    second_task = controller.enqueue_task(
        draft=ExecutionTaskDraft(source="manual_input", source_summary="手动输入"),
        summary="第二次任务",
    )

    assert controller.draft_queue_size() == 1
    assert controller.find_task_by_id(first_task.task_id) is None
    assert controller.find_task_by_id(second_task.task_id) is not None


def test_execution_queue_controller_cancel_active_task_marks_task_cancelled(monkeypatch) -> None:
    controller = _build_controller(single_task_mode=True)

    monkeypatch.setattr(controller, "start_task_worker", lambda _task: None)
    queued_task = controller.enqueue_task(
        draft=ExecutionTaskDraft(source="manual_input", source_summary="手动输入"),
        summary="测试任务",
    )
    worker = _FakeExecutionThread(wait_result=False)
    controller._active_worker = worker

    feedbacks = []
    controller.feedback_requested.connect(feedbacks.append)

    assert controller.cancel_active_task() is True

    cancelled_task = controller.find_task_by_id(queued_task.task_id)
    assert cancelled_task is not None
    assert cancelled_task.status == TASK_STATUS_CANCELLED
    assert controller.active_task_id is None
    assert controller.has_active_background_work() is False
    assert "terminate" in worker.calls
    assert feedbacks[-1].title == "任务已取消"


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


def test_execution_queue_controller_finishing_task_does_not_keep_background_wav_state(monkeypatch) -> None:
    controller = _build_controller()
    feedbacks = []
    controller.feedback_requested.connect(feedbacks.append)
    monkeypatch.setattr(controller, "start_task_worker", lambda _task: None)

    queued_task = controller.enqueue_task(
        draft=ExecutionTaskDraft(source="manual_input", source_summary="手动输入"),
        summary="测试任务",
    )

    controller.on_task_finished(
        queued_task.task_id,
        ExecutionTaskResult(
            completed_steps=("音频解包", "音频转码", "事件映射"),
            summary="执行完成",
            duration_seconds=1.2,
        ),
    )

    assert controller.has_active_background_work() is False
    assert all(feedback.title != "WAV 转码后台继续" for feedback in feedbacks)


def test_execution_queue_controller_shutdown_without_background_wav_processes_stays_clean() -> None:
    controller = _build_controller()

    controller.shutdown()

    assert controller.has_active_background_work() is False
