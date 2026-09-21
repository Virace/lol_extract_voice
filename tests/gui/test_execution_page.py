"""执行中心页面交互回归测试。"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from lol_audio_unpack.app.resource_pack import ResourcePackWadRef, build_resource_pack_key
from lol_audio_unpack.app.results import ResultStatus, RunResult, StageResult
from lol_audio_unpack.gui.shared_data import (
    SharedDataPhase,
    SharedDataProblem,
    SharedDataProblemCode,
    SharedDataState,
)
from lol_audio_unpack.gui.task_models import (
    AppContextInputSnapshot,
    ExecutionTaskDraft,
    ExecutionTaskParamsSnapshot,
    ExecutionTaskProgress,
    ExecutionTaskResult,
)
from lol_audio_unpack.gui.view.execution_page import ExecutionPage
from lol_audio_unpack.gui.view.setting_page import SettingPage

EXPECTED_WAV_WORKERS = 8
EXPECTED_WAV_TIMEOUT = 15
EXPECTED_WAV_RETRIES = 5


def _start_silent_task(qtbot, monkeypatch):
    """隔离后台进程，让真实页面在没有进度事件时运行。"""
    clock = [100.0]
    monkeypatch.setattr("lol_audio_unpack.gui.view.execution_page.monotonic", lambda: clock[0])
    page = ExecutionPage()
    qtbot.addWidget(page)
    monkeypatch.setattr(page._queue_controller, "start_task_worker", lambda _task: None)
    page.set_shared_data_state(SharedDataState(SharedDataPhase.READY, 1))
    draft = ExecutionTaskDraft(
        source="default_scope",
        source_summary="英雄任务",
        context_input=AppContextInputSnapshot(),
        task_params=ExecutionTaskParamsSnapshot(),
    )
    page.submit_task(draft)
    return page, clock, draft


def test_elapsed_time_advances_without_progress_and_survives_stage_changes(qtbot, monkeypatch) -> None:
    """隐藏执行页也应持续发布整轮耗时，阶段计数清零不能重置时钟。"""
    page, clock, draft = _start_silent_task(qtbot, monkeypatch)
    published = []
    page.global_progress_state_changed.connect(published.append)
    initial = page.current_global_progress_state()
    clock[0] = 102.4

    qtbot.waitUntil(lambda: page.current_global_progress_state().rate_text == "已运行 2.4s", timeout=1500)

    assert published[-1] == page.current_global_progress_state()
    assert (published[-1].progress_current, published[-1].progress_total) == (
        initial.progress_current,
        initial.progress_total,
    )
    assert published[-1].detail_text == initial.detail_text
    controller = page._queue_controller
    task_id = controller.active_task_id
    for stage, current in (("extract", 2), ("mapping", 0)):
        controller.on_task_progress(
            task_id,
            ExecutionTaskProgress(stage, stage, "英雄", current=current, total=5),
        )
        assert page.current_global_progress_state().rate_text == "已运行 2.4s"

    clock[0] = 107.6
    qtbot.waitUntil(lambda: page.current_global_progress_state().rate_text == "已运行 7.6s", timeout=1500)
    assert page.current_global_progress_state().progress_current == 0
    controller.cancel_active_task()
    page.submit_task(draft)
    assert page.current_global_progress_state().rate_text == "已运行 0.0s"
    controller.cancel_active_task()


@pytest.mark.parametrize("outcome", ["success", "partial", "failed", "cancelled", "worker_error"])
def test_elapsed_time_freezes_at_terminal_state(qtbot, monkeypatch, outcome) -> None:
    """所有终态都应保存结束瞬间的总耗时，并停止后续刷新。"""
    page, clock, _draft = _start_silent_task(qtbot, monkeypatch)
    controller = page._queue_controller
    task_id = controller.active_task_id
    controller.on_task_progress(task_id, ExecutionTaskProgress("extract", "音频解包", "英雄", current=2, total=5))
    clock[0] = 112.3
    if outcome == "cancelled":
        controller.cancel_active_task()
    elif outcome == "worker_error":
        controller.on_task_failed(task_id, "后台异常退出")
    else:
        controller.on_task_finished(
            task_id,
            ExecutionTaskResult(
                (),
                "任务结束",
                12.0,
                RunResult((StageResult("extract", status=ResultStatus(outcome)),)),
            ),
        )

    terminal = page.current_global_progress_state()
    assert terminal.visible is False
    assert terminal.rate_text == "总耗时 12.3s"
    if outcome == "cancelled":
        assert (terminal.progress_current, terminal.progress_total) == (2, 5)
    published = []
    page.global_progress_state_changed.connect(published.append)
    clock[0] = 200.0
    qtbot.wait(250)
    assert page.current_global_progress_state() == terminal
    assert published == []


def _build_linked_pages(qtbot) -> tuple[SettingPage, ExecutionPage]:
    """创建共用同一份 GuiConfig 的设置页与执行中心。"""
    setting_page = SettingPage()
    execution_page = ExecutionPage()
    qtbot.addWidget(setting_page)
    qtbot.addWidget(execution_page)
    execution_page.set_gui_config(setting_page.config)
    return setting_page, execution_page


def test_execution_page_uses_latest_wav_defaults_from_setting_page(qtbot) -> None:
    """设置页变更后的 WAV 默认值应直接体现在任务草稿中。"""
    setting_page, execution_page = _build_linked_pages(qtbot)

    setting_page.wavWorkersCard.comboBox.setCurrentText(str(EXPECTED_WAV_WORKERS))
    setting_page.wavTimeoutCard.comboBox.setCurrentText(str(EXPECTED_WAV_TIMEOUT))
    setting_page.wavRetriesCard.comboBox.setCurrentText(str(EXPECTED_WAV_RETRIES))

    execution_page.advancedPanel.wav_task_cb.setChecked(True)
    execution_page.advancedPanel.wav_format_combo.setCurrentText("float")
    execution_page.taskBuilderPanel.sync_state_from_widgets()

    draft = execution_page.taskBuilderPanel.build_task_draft(gui_config=execution_page.gui_config)

    assert draft.task_params.wav_enabled is True
    assert draft.task_params.wav_workers == EXPECTED_WAV_WORKERS
    assert draft.task_params.wav_timeout == EXPECTED_WAV_TIMEOUT
    assert draft.task_params.to_operation_options().wav_output.max_retries == EXPECTED_WAV_RETRIES
    assert draft.task_params.wav_format == "float"


def test_execution_page_normalizes_synced_full_selection_to_default_scope(qtbot) -> None:
    """总览页同步的整页全选在执行中心应等价于默认全量。"""
    page = ExecutionPage()
    qtbot.addWidget(page)
    page.set_entity_data("champions", [{"id": "1"}, {"id": "103"}])
    page.set_entity_data("maps", [{"id": "11"}])

    summary = page.set_selected_entities(
        {
            "source": "overview_selection",
            "champion_ids": (1, 103),
            "map_ids": (11,),
            "summary": "已同步全部实体。",
        }
    )
    draft = page.taskBuilderPanel.build_task_draft(gui_config=page.gui_config)

    assert summary == "已同步全部实体。"
    assert page.taskBuilderPanel.current_target_ids() == (("1", "103"), ("11",))
    assert draft.task_params.champion_ids is None
    assert draft.task_params.map_ids is None


def test_execution_page_treats_changed_resource_pack_snapshot_as_selection_conflict(qtbot, monkeypatch) -> None:
    """相同资源包 key 的 WAD stat snapshot 变化也必须经同步冲突处理。"""
    page = ExecutionPage()
    qtbot.addWidget(page)
    key = build_resource_pack_key("Legacy.wad.client", "MODE_LEGACY")
    first = ResourcePackWadRef("Game/DATA/FINAL/Legacy.wad.client", size=12, mtime_ns=34)
    second = ResourcePackWadRef("Game/DATA/FINAL/Legacy.wad.client", size=12, mtime_ns=56)
    choices = []
    monkeypatch.setattr(
        "lol_audio_unpack.gui.view.execution_page.ask_selection_conflict_resolution",
        lambda **kwargs: choices.append(kwargs) or "replace",
    )

    page.set_selected_entities(
        {
            "source": "overview_selection",
            "champion_ids": (),
            "map_ids": (),
            "special_targets": (key,),
            "special_target_names": ("历史资源包 · Legacy",),
            "resource_pack_wads": (first,),
            "summary": "首次同步。",
        }
    )
    page.set_selected_entities(
        {
            "source": "overview_selection",
            "champion_ids": (),
            "map_ids": (),
            "special_targets": (key,),
            "special_target_names": ("历史资源包 · Legacy",),
            "resource_pack_wads": (second,),
            "summary": "重新同步。",
        }
    )

    assert len(choices) == 1
    assert page.taskBuilderPanel.current_resource_pack_wads() == (second,)


def test_execution_page_primary_button_cancels_running_task(qtbot, monkeypatch) -> None:
    """任务启动后主按钮应切换为取消，并把点击路由到停止动作。"""
    _setting_page, execution_page = _build_linked_pages(qtbot)
    monkeypatch.setattr("lol_audio_unpack.gui.view.execution_page.get_block_reason", lambda _cfg: None)
    monkeypatch.setattr(execution_page._queue_controller, "start_task_worker", lambda _task: None)
    execution_page.set_shared_data_state(SharedDataState(SharedDataPhase.READY, 1))

    execution_page._queue_task_draft()

    assert execution_page.create_task_btn.text() == "取消"

    cancelled = []
    monkeypatch.setattr(execution_page, "_confirm_force_stop_task", lambda: True)
    monkeypatch.setattr(
        execution_page._queue_controller,
        "cancel_active_task",
        lambda: cancelled.append(True) or True,
    )

    qtbot.mouseClick(execution_page.create_task_btn, Qt.MouseButton.LeftButton)

    assert cancelled == [True]


def test_execution_page_blocks_tasks_across_shared_data_states(qtbot, monkeypatch) -> None:
    """共享数据准备中或失败后，都不应创建不可执行任务。"""
    _setting_page, execution_page = _build_linked_pages(qtbot)
    started_tasks = []
    monkeypatch.setattr("lol_audio_unpack.gui.view.execution_page.get_block_reason", lambda _cfg: None)
    monkeypatch.setattr(execution_page._queue_controller, "start_task_worker", started_tasks.append)

    execution_page.set_shared_data_state(SharedDataState(SharedDataPhase.PREPARING, 1))
    execution_page._queue_task_draft()

    assert execution_page.create_task_btn.text() == "准备数据中"
    assert "正在修复" in execution_page.create_task_btn.toolTip()
    assert execution_page.create_task_btn.isEnabled() is False
    assert execution_page._queue_controller.draft_queue_size() == 0

    execution_page.set_shared_data_state(
        SharedDataState(
            SharedDataPhase.FAILED,
            1,
            problem=SharedDataProblem(
                SharedDataProblemCode.BANK_ARTIFACT_MISSING,
                "maps",
                "地图 banks 未生成",
            ),
        )
    )
    execution_page._queue_task_draft()

    assert execution_page.create_task_btn.text() == "创建任务"
    assert "地图 banks 未生成" in execution_page.create_task_btn.toolTip()
    assert execution_page.create_task_btn.isEnabled() is False
    assert execution_page._queue_controller.draft_queue_size() == 0
    assert started_tasks == []


def test_execution_page_only_enables_task_creation_when_shared_data_is_ready(qtbot) -> None:
    """等待、部分可用与就绪三态必须由 phase 直接决定按钮门禁。"""
    _setting_page, execution_page = _build_linked_pages(qtbot)

    execution_page.set_shared_data_state(SharedDataState(SharedDataPhase.WAITING, 2))
    assert execution_page.create_task_btn.text() == "等待当前任务结束"
    assert execution_page.create_task_btn.isEnabled() is False

    execution_page.set_shared_data_state(SharedDataState(SharedDataPhase.PARTIAL, 2))
    assert execution_page.create_task_btn.text() == "创建任务"
    assert execution_page.create_task_btn.isEnabled() is False

    execution_page.set_shared_data_state(SharedDataState(SharedDataPhase.READY, 2))
    assert execution_page.create_task_btn.isEnabled() is True
    assert execution_page.create_task_btn.toolTip() == ""
