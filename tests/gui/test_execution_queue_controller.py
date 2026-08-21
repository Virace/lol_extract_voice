"""执行中心队列状态机控制器测试。"""

from __future__ import annotations

import pytest

from lol_audio_unpack.app.resource_pack import ResourcePackWadRef, build_resource_pack_key
from lol_audio_unpack.app.results import EntityResult, ResultStatus, RunResult, StageResult
from lol_audio_unpack.gui.controllers.execution_queue import ExecutionQueueController
from lol_audio_unpack.gui.task_models import (
    TASK_STATUS_CANCELLED,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_PARTIAL,
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


def _task_result(
    *stages: StageResult,
    completed_steps: tuple[str, ...] = (),
    summary: str = "执行完成",
) -> ExecutionTaskResult:
    """构造携带权威整轮结果的 GUI 任务结果。"""
    return ExecutionTaskResult(
        completed_steps=completed_steps,
        summary=summary,
        duration_seconds=1.2,
        run_result=RunResult(stages),
    )


def _entity_result(
    stage: str,
    entity_type: str,
    entity_id: int | str,
    status: ResultStatus,
    *artifacts: str,
) -> StageResult:
    """构造单实体阶段结果。"""
    return StageResult.from_entities(
        stage,
        (EntityResult(entity_type, entity_id, status, artifacts=artifacts),),
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
        _task_result(
            StageResult.from_entities(
                "extract",
                (
                    EntityResult("champion", 1, ResultStatus.SUCCESS, artifacts=("audios/1.wem",)),
                    EntityResult("champion", 103, ResultStatus.SUCCESS, artifacts=("audios/103.wem",)),
                ),
            ),
            completed_steps=("音频解包",),
        ),
    )

    completed_payload = controller.find_task_by_id(queued_task.task_id)
    assert completed_payload is not None
    assert completed_payload.status == TASK_STATUS_COMPLETED
    assert completed_payload.progress_current == completed_payload.progress_total
    assert controller.active_task_id is None
    assert refresh_requests == [OutputStateRefreshRequest(champion_ids=("1", "103"))]


def test_execution_queue_controller_keeps_resource_pack_key_and_snapshot_for_refresh(monkeypatch) -> None:
    """任务完成后的增量刷新必须同时保留资源包 key 与来源 snapshot。"""
    controller = _build_controller()
    key = build_resource_pack_key("Legacy.wad.client", "MODE_LEGACY")
    ref = ResourcePackWadRef("Game/DATA/FINAL/Legacy.wad.client", size=12, mtime_ns=34)
    monkeypatch.setattr(controller, "start_task_worker", lambda _task: None)
    refresh_requests = []
    controller.output_state_refresh_requested.connect(refresh_requests.append)
    task = controller.enqueue_task(
        draft=ExecutionTaskDraft(
            source="overview_selection",
            source_summary="历史资源包",
            task_params=ExecutionTaskParamsSnapshot(
                special_targets=(key,),
                resource_pack_wads=(ref,),
            ),
        ),
        summary="资源包任务",
    )

    controller.on_task_finished(
        task.task_id,
        _task_result(
            _entity_result("extract", "resource_pack", key, ResultStatus.SUCCESS, "audios/pack/101.wem"),
            completed_steps=("音频解包",),
        ),
    )

    assert refresh_requests == [OutputStateRefreshRequest(special_targets=(key,), resource_pack_wads=(ref,))]


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
        _task_result(
            _entity_result("extract", "champion", 1, ResultStatus.SUCCESS, "audios/1.wem"),
            completed_steps=("音频解包",),
        ),
    )

    second_task = controller.enqueue_task(
        draft=ExecutionTaskDraft(source="manual_input", source_summary="手动输入"),
        summary="第二次任务",
    )

    assert controller.draft_queue_size() == 1
    assert controller.find_task_by_id(first_task.task_id) is None
    assert controller.find_task_by_id(second_task.task_id) is not None


def test_execution_queue_controller_maps_partial_result_to_warning_and_bounded_refresh(monkeypatch) -> None:
    """partial 必须进入独立终态，并只刷新带落盘证据的成功实体。"""
    controller = _build_controller(single_task_mode=True)
    monkeypatch.setattr(controller, "start_task_worker", lambda _task: None)
    task = controller.enqueue_task(
        draft=ExecutionTaskDraft(
            source="manual_input",
            source_summary="手动输入",
            task_params=ExecutionTaskParamsSnapshot(champion_ids=(1, 2)),
        ),
        summary="测试任务",
    )
    controller.update_task(task.task_id, progress_current=1, progress_total=2)
    feedbacks = []
    progress_updates = []
    refresh_requests = []
    controller.feedback_requested.connect(feedbacks.append)
    controller.progress_display_requested.connect(progress_updates.append)
    controller.output_state_refresh_requested.connect(refresh_requests.append)
    partial_stage = StageResult.from_entities(
        "extract",
        (
            EntityResult("champion", 1, ResultStatus.SUCCESS, artifacts=("audios/1.wem",)),
            EntityResult("champion", 2, ResultStatus.FAILED),
        ),
    )

    controller.on_task_finished(
        task.task_id,
        _task_result(partial_stage, completed_steps=("音频解包",), summary="部分完成：成功 1，失败 1"),
    )

    updated_task = controller.find_task_by_id(task.task_id)
    assert updated_task is not None
    assert updated_task.status == TASK_STATUS_PARTIAL
    assert controller.queue_status_counts()[TASK_STATUS_PARTIAL] == 1
    assert feedbacks[-1].title == "任务部分完成"
    assert feedbacks[-1].level == "warning"
    assert progress_updates[-1].progress_current < progress_updates[-1].progress_total
    assert controller.has_incomplete_tasks() is False
    assert refresh_requests == [OutputStateRefreshRequest(champion_ids=("1",))]


def test_execution_queue_controller_failed_result_without_artifacts_does_not_refresh(monkeypatch) -> None:
    """失败结果没有落盘证据时不得猜测刷新范围，也不得显示满进度。"""
    controller = _build_controller(single_task_mode=True)
    monkeypatch.setattr(controller, "start_task_worker", lambda _task: None)
    task = controller.enqueue_task(
        draft=ExecutionTaskDraft(source="manual_input", source_summary="手动输入"),
        summary="测试任务",
    )
    feedbacks = []
    progress_updates = []
    refresh_requests = []
    controller.feedback_requested.connect(feedbacks.append)
    controller.progress_display_requested.connect(progress_updates.append)
    controller.output_state_refresh_requested.connect(refresh_requests.append)

    controller.on_task_finished(
        task.task_id,
        _task_result(
            _entity_result("extract", "champion", 1, ResultStatus.FAILED),
            summary="执行失败：英雄 1 解包失败",
        ),
    )

    updated_task = controller.find_task_by_id(task.task_id)
    assert updated_task is not None
    assert updated_task.status == TASK_STATUS_FAILED
    assert feedbacks[-1].title == "任务执行失败"
    assert feedbacks[-1].level == "error"
    assert progress_updates[-1].progress_current < progress_updates[-1].progress_total
    assert refresh_requests == []
    assert controller.has_incomplete_tasks() is False


def test_execution_queue_controller_failed_result_refreshes_only_confirmed_artifact(monkeypatch) -> None:
    """失败实体若明确记录了落盘产物，只允许刷新该实体。"""
    controller = _build_controller(single_task_mode=True)
    monkeypatch.setattr(controller, "start_task_worker", lambda _task: None)
    task = controller.enqueue_task(
        draft=ExecutionTaskDraft(
            source="manual_input",
            source_summary="手动输入",
            task_params=ExecutionTaskParamsSnapshot(champion_ids=(1, 2)),
        ),
        summary="测试任务",
    )
    refresh_requests = []
    controller.output_state_refresh_requested.connect(refresh_requests.append)

    controller.on_task_finished(
        task.task_id,
        _task_result(
            StageResult.from_entities(
                "extract",
                (
                    EntityResult(
                        "champion",
                        1,
                        ResultStatus.FAILED,
                        artifacts=("audios/1/partial.wem",),
                    ),
                    EntityResult("champion", 2, ResultStatus.FAILED),
                ),
            ),
            summary="执行失败：2 个实体失败",
        ),
    )

    assert refresh_requests == [OutputStateRefreshRequest(champion_ids=("1",))]


def test_execution_queue_controller_maps_typed_cancelled_without_refresh(monkeypatch) -> None:
    """后端返回 cancelled 时应进入已取消终态，且无产物证据时不刷新。"""
    controller = _build_controller(single_task_mode=True)
    monkeypatch.setattr(controller, "start_task_worker", lambda _task: None)
    task = controller.enqueue_task(
        draft=ExecutionTaskDraft(source="manual_input", source_summary="手动输入"),
        summary="测试任务",
    )
    feedbacks = []
    refresh_requests = []
    controller.feedback_requested.connect(feedbacks.append)
    controller.output_state_refresh_requested.connect(refresh_requests.append)

    controller.on_task_finished(
        task.task_id,
        _task_result(StageResult.cancelled("extract"), summary="已取消：用户中断操作"),
    )

    updated_task = controller.find_task_by_id(task.task_id)
    assert updated_task is not None
    assert updated_task.status == TASK_STATUS_CANCELLED
    assert updated_task.progress_current < updated_task.progress_total
    assert feedbacks[-1].title == "任务已取消"
    assert feedbacks[-1].level == "warning"
    assert refresh_requests == []


def test_execution_queue_controller_cancel_active_task_marks_task_cancelled(monkeypatch) -> None:
    controller = _build_controller(single_task_mode=True)

    monkeypatch.setattr(controller, "start_task_worker", lambda _task: None)
    queued_task = controller.enqueue_task(
        draft=ExecutionTaskDraft(source="manual_input", source_summary="手动输入"),
        summary="测试任务",
    )
    controller.update_task(queued_task.task_id, progress_current=1, progress_total=1)
    worker = _FakeExecutionThread(wait_result=False)
    controller._active_worker = worker

    feedbacks = []
    refresh_requests = []
    controller.feedback_requested.connect(feedbacks.append)
    controller.output_state_refresh_requested.connect(refresh_requests.append)

    assert controller.cancel_active_task() is True

    cancelled_task = controller.find_task_by_id(queued_task.task_id)
    assert cancelled_task is not None
    assert cancelled_task.status == TASK_STATUS_CANCELLED
    assert cancelled_task.progress_current < cancelled_task.progress_total
    assert controller.active_task_id is None
    assert controller.has_active_background_work() is False
    assert "terminate" in worker.calls
    assert feedbacks[-1].title == "任务已取消"
    assert refresh_requests == []


def test_execution_queue_controller_worker_failure_never_finishes_at_full_progress(monkeypatch) -> None:
    controller = _build_controller(single_task_mode=True)
    monkeypatch.setattr(controller, "start_task_worker", lambda _task: None)
    queued_task = controller.enqueue_task(
        draft=ExecutionTaskDraft(source="manual_input", source_summary="手动输入"),
        summary="测试任务",
    )
    controller.update_task(queued_task.task_id, progress_current=1, progress_total=1)
    progress_updates = []
    controller.progress_display_requested.connect(progress_updates.append)

    controller.on_task_failed(queued_task.task_id, "worker crashed")

    failed_task = controller.find_task_by_id(queued_task.task_id)
    assert failed_task is not None
    assert failed_task.status == TASK_STATUS_FAILED
    assert failed_task.progress_current == 0
    assert failed_task.progress_total == 1
    assert progress_updates[-1].progress_current < progress_updates[-1].progress_total


@pytest.mark.parametrize(
    ("status", "expected_status", "expected_level", "expects_full_progress", "expects_refresh"),
    (
        ("success", TASK_STATUS_COMPLETED, "success", True, True),
        ("partial", TASK_STATUS_PARTIAL, "warning", False, True),
        ("failed", TASK_STATUS_FAILED, "error", False, False),
        ("cancelled", TASK_STATUS_CANCELLED, "warning", False, False),
    ),
)
def test_execution_queue_controller_simulates_typed_terminal_result_for_manual_review(
    status: str,
    expected_status: str,
    expected_level: str,
    expects_full_progress: bool,
    expects_refresh: bool,
) -> None:
    controller = _build_controller(single_task_mode=True)
    feedbacks = []
    refresh_requests = []
    controller.feedback_requested.connect(feedbacks.append)
    controller.output_state_refresh_requested.connect(refresh_requests.append)

    message = controller.simulate_terminal_result(status)

    task = controller.find_task_by_id(1)
    assert task is not None
    assert task.status == expected_status
    assert (task.progress_current == task.progress_total) is expects_full_progress
    assert feedbacks[-1].level == expected_level
    assert bool(refresh_requests) is expects_refresh
    assert controller.has_incomplete_tasks() is False
    assert status in message


def test_execution_queue_controller_shutdown_clears_active_state() -> None:
    controller = _build_controller()
    controller._active_task_id = 1
    controller._active_worker = object()

    assert controller.has_active_background_work() is True

    controller.shutdown()

    assert controller.has_active_background_work() is False
    assert controller.active_task_id is None
