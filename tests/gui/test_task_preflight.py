"""验证启动前决定、快照替换和迟到结果隔离。"""

from __future__ import annotations

from threading import Event

import pytest

from lol_audio_unpack.app.audio_export import AudioExportRequest, ExportTarget
from lol_audio_unpack.app.audio_scope import AudioScope
from lol_audio_unpack.app.types import WavOutputOptions
from lol_audio_unpack.config import SettingKey
from lol_audio_unpack.gui.controllers.execution_queue import ExecutionQueueController
from lol_audio_unpack.gui.service import task_preflight
from lol_audio_unpack.gui.service.task_preflight import use_builtin
from lol_audio_unpack.gui.task_models import (
    TASK_STATUS_CANCELLED,
    AppContextInputSnapshot,
    ExecutionTaskDraft,
    QueuedExecutionTask,
)
from lol_audio_unpack.runtime.probe import ToolProbe


def test_external_failure_waits_and_builtin_is_rechecked(qtbot, monkeypatch) -> None:
    """失败不启动 worker，确认只修改任务快照，内置也必须重新探测。"""
    controller = ExecutionQueueController(build_task_item_tooltip=lambda task: "")
    initial = []
    monkeypatch.setattr(controller, "start_task_worker", initial.append)
    original = ExecutionTaskDraft(
        "test", "sample", context_input=AppContextInputSnapshot(((SettingKey.WWISER_PATH, "tool.pyz"),))
    )
    task = controller.enqueue_task(draft=original, summary="sample")
    launched = []
    monkeypatch.setattr(controller, "_start_execution", launched.append)
    issue = ToolProbe("hirc", "tool.pyz", "exit", "parse failed")
    with qtbot.waitSignal(controller.preflight_decision_requested):
        controller._finish_preflight(task, (issue,))
    assert not launched

    controller.resolve_preflight(task.task_id, builtin=True)
    assert len(initial) == 2  # noqa: PLR2004
    revised = initial[-1]
    assert revised.draft.context_input.to_settings()[SettingKey.WWISER_PATH] == ""
    assert original.context_input.to_settings()[SettingKey.WWISER_PATH] == "tool.pyz"
    assert not revised.draft.tools_checked
    controller._finish_preflight(revised, (ToolProbe("hirc", None),))
    assert len(launched) == 1
    assert launched[0].draft.tools_checked


def test_existing_export_ignores_game_source_and_unused_wwiser(tmp_path, monkeypatch) -> None:
    """已有音频只检查实际转码器，不依赖当前空语言或无效 WWISER。"""
    root = tmp_path / "16.18"
    root.mkdir()
    (root / "1.wem").write_bytes(b"existing")
    request = AudioExportRequest(
        "champion",
        "1",
        "Annie",
        "16.18",
        root,
        (ExportTarget(AudioScope(root, files=("1.wem",)), tmp_path / "out"),),
        tmp_path / "reports",
        WavOutputOptions(enabled=True),
    )
    task = QueuedExecutionTask(
        1,
        ExecutionTaskDraft(
            "export",
            "Annie",
            export_request=request,
            context_input=AppContextInputSnapshot(
                ((SettingKey.WWISER_PATH, "missing.pyz"), (SettingKey.GAME_REGION, ""))
            ),
        ),
        "Annie",
    )
    calls = []
    monkeypatch.setattr(
        task_preflight, "probe_tool", lambda tool, **kwargs: calls.append(tool) or ToolProbe(tool, None)
    )
    results = task_preflight.check_task(task, Event())
    assert all(item.success for item in results)
    assert calls == ["wav"]


def test_cancelled_probe_cannot_start_task_or_release_gate_early(qtbot, monkeypatch) -> None:
    """等待取消完成期间仍持有门禁；迟到成功不会启动处理。"""
    controller = ExecutionQueueController(build_task_item_tooltip=lambda task: "")
    monkeypatch.setattr(controller, "start_task_worker", lambda task: None)
    task = controller.enqueue_task(draft=ExecutionTaskDraft("test", "sample"), summary="sample")
    controller._probe_cancel = Event()
    controller._probe_worker = object()
    launched = []
    monkeypatch.setattr(controller, "_start_execution", launched.append)
    assert controller.cancel_active_task()
    assert controller.is_task_running()
    controller._finish_preflight(task, (ToolProbe("wav", None),))
    assert not controller.is_task_running()
    assert controller.find_task_by_id(task.task_id).status == TASK_STATUS_CANCELLED
    controller._finish_preflight(task, (ToolProbe("wav", None),))
    assert not launched
