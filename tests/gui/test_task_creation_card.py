"""执行中心任务创建卡片测试。"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt

from lol_audio_unpack.app.resource_pack import ResourcePackWadRef
from lol_audio_unpack.gui.task_models import AppContextInputSnapshot
from lol_audio_unpack.gui.view.execution.task_creation_card import TaskCreationCard

EXPECTED_WAV_WORKERS = 6
EXPECTED_WAV_TIMEOUT = 9
EXPECTED_WAV_RETRIES = 4
EXPECTED_GAME_PATH = "game-root"
EXPECTED_OUTPUT_PATH = "output-root"


@dataclass(slots=True)
class _FakeGuiConfig:
    """任务表单测试使用的最小 GUI 配置替身。"""

    wav_enabled: bool = True
    wav_workers: int = EXPECTED_WAV_WORKERS
    wav_timeout: int = EXPECTED_WAV_TIMEOUT
    wav_retries: int = EXPECTED_WAV_RETRIES
    wav_format: str = "float"

    def to_app_context_input_snapshot(self) -> AppContextInputSnapshot:
        """返回最小共享上下文快照。"""
        return AppContextInputSnapshot(
            settings=(
                ("SOURCE_MODE", "local_path"),
                ("GAME_PATH", EXPECTED_GAME_PATH),
                ("OUTPUT_PATH", EXPECTED_OUTPUT_PATH),
                ("GAME_REGION", "zh_CN"),
            )
        )


def _build_panel(qtbot) -> TaskCreationCard:
    """创建任务创建卡片。"""
    panel = TaskCreationCard()
    qtbot.addWidget(panel)
    return panel


def test_task_creation_card_uses_gui_wav_defaults_for_draft(qtbot) -> None:
    """显式启用音频转码时，任务草稿应携带默认转码参数。"""
    panel = _build_panel(qtbot)
    gui_config = _FakeGuiConfig()

    panel.apply_gui_config_defaults(gui_config)
    panel.apply_defaults()
    panel.wav_task_cb.setChecked(True)
    panel.sync_state_from_widgets()

    draft = panel.build_task_draft(gui_config=gui_config)
    operation_options = draft.task_params.to_operation_options()

    assert draft.task_params.wav_enabled is True
    assert draft.task_params.wav_workers == EXPECTED_WAV_WORKERS
    assert draft.task_params.wav_timeout == EXPECTED_WAV_TIMEOUT
    assert draft.task_params.wav_retries == EXPECTED_WAV_RETRIES
    assert draft.task_params.wav_format == "float"
    assert operation_options.wav_output.enabled is True
    assert operation_options.wav_output.worker_count == EXPECTED_WAV_WORKERS
    assert operation_options.wav_output.timeout_seconds == EXPECTED_WAV_TIMEOUT
    assert operation_options.wav_output.max_retries == EXPECTED_WAV_RETRIES
    assert operation_options.wav_output.format == "float"


def test_task_creation_card_preserves_independent_wav_action_state(qtbot) -> None:
    """WAV 默认不自动执行，但应允许作为独立动作启用。"""
    panel = _build_panel(qtbot)
    gui_config = _FakeGuiConfig(wav_enabled=True)

    panel.apply_gui_config_defaults(gui_config)
    panel.apply_defaults()
    panel.sync_state_from_widgets()

    draft = panel.build_task_draft(gui_config=gui_config)

    assert panel.wav_task_cb.isChecked() is False
    assert draft.task_params.wav_enabled is False

    panel.extract_task_cb.setChecked(False)
    panel.wav_task_cb.setChecked(True)
    panel.sync_state_from_widgets()

    draft = panel.build_task_draft(gui_config=gui_config)

    assert draft.task_params.run_extract is False
    assert draft.task_params.wav_enabled is True


def test_task_creation_card_updates_synced_full_selection_after_manual_edit(qtbot) -> None:
    """全量同步应归一为空 target，用户手改后恢复为显式 ID。"""
    panel = _build_panel(qtbot)
    gui_config = _FakeGuiConfig()

    panel.apply_selected_entities(
        champion_ids=("1", "103"),
        map_ids=("11",),
        source="overview_selection",
        summary="已同步全部实体。",
        select_all=True,
    )

    draft = panel.build_task_draft(gui_config=gui_config)

    assert draft.task_params.champion_ids is None
    assert draft.task_params.map_ids is None

    panel.champion_ids_input.setText("1")
    panel.sync_state_from_widgets()

    draft = panel.build_task_draft(gui_config=gui_config)

    assert draft.task_params.champion_ids == (1,)
    assert draft.task_params.map_ids == (11,)


def test_task_creation_card_restore_button_resets_custom_inputs_to_defaults(qtbot) -> None:
    """恢复按钮应把自定义输入恢复到默认值。"""
    panel = _build_panel(qtbot)

    panel.champion_ids_input.setText("1,103")
    panel.map_ids_input.setText("11")
    panel.vo_filter.setCurrentItem("ALL")
    panel.max_workers_combo.setCurrentText("16")
    panel.bp_voice_cb.setChecked(False)
    panel.force_update_cb.setChecked(True)
    panel.integrate_data_cb.setChecked(False)
    panel.wav_task_cb.setChecked(True)
    panel.wav_format_combo.setCurrentText("float")
    panel.sync_state_from_widgets()

    qtbot.mouseClick(panel.restore_defaults_btn, Qt.MouseButton.LeftButton)

    assert panel.champion_ids_input.text() == ""
    assert panel.map_ids_input.text() == ""
    assert panel.vo_filter.currentRouteKey() == "VO"
    assert panel.max_workers_combo.currentText() == "4"
    assert panel.bp_voice_cb.isChecked() is True
    assert panel.force_update_cb.isChecked() is False
    assert panel.integrate_data_cb.isChecked() is True
    assert panel.wav_task_cb.isChecked() is False
    assert panel.wav_format_combo.currentText() == "pcm16"


def test_task_creation_card_discards_synced_special_targets_after_manual_id_edit(qtbot) -> None:
    """用户手改普通 ID 后，隐藏的特殊 key 不能继续进入任务草稿。"""
    panel = _build_panel(qtbot)
    gui_config = _FakeGuiConfig()
    ref = ResourcePackWadRef("Game/DATA/FINAL/Legacy.wad.client", size=12, mtime_ns=34)

    panel.apply_selected_entities(
        champion_ids=("1",),
        map_ids=(),
        special_targets=("champion:66600",),
        special_target_names=("末日人机 · 厄加特",),
        resource_pack_wads=(ref,),
        source="overview_selection",
        summary="已同步特殊内容。",
    )
    assert "末日人机 · 厄加特" in panel.target_summary_value.text()

    panel.champion_ids_input.setText("103")
    panel.sync_state_from_widgets()
    draft = panel.build_task_draft(gui_config=gui_config)

    assert panel.current_special_targets() == ()
    assert panel.current_resource_pack_wads() == ()
    assert "特殊内容 0 个" in panel.target_summary_value.text()
    assert draft.task_params.special_targets == ()
    assert draft.task_params.resource_pack_wads == ()


def test_task_creation_card_preserves_synced_resource_pack_wad_snapshot(qtbot) -> None:
    """资源包 key 与 WAD snapshot 必须一起进入不可变任务草稿。"""
    panel = _build_panel(qtbot)
    gui_config = _FakeGuiConfig()
    ref = ResourcePackWadRef("Game/DATA/FINAL/Legacy.wad.client", size=12, mtime_ns=34)

    panel.apply_selected_entities(
        champion_ids=(),
        map_ids=(),
        special_targets=("resource_pack:legacy:mode_legacy",),
        special_target_names=("历史资源包 · Legacy",),
        resource_pack_wads=(ref,),
        source="overview_selection",
        summary="已同步历史资源包。",
    )

    draft = panel.build_task_draft(gui_config=gui_config)

    assert draft.task_params.special_targets == ("resource_pack:legacy:mode_legacy",)
    assert draft.task_params.resource_pack_wads == (ref,)


def test_task_creation_card_counts_special_targets_without_display_names(qtbot) -> None:
    """兼容旧同步输入缺少名称时，范围摘要仍应显示 special 数量且不泄露 key。"""
    panel = _build_panel(qtbot)

    panel.apply_selected_entities(
        champion_ids=(),
        map_ids=(),
        special_targets=("champion:66600",),
        special_target_names=(),
        source="overview_selection",
        summary="已同步特殊内容。",
    )

    summary = panel.target_summary_value.text()
    assert "特殊内容 1 个" in summary
    assert "全部英雄+地图" not in summary
    assert "champion:66600" not in summary
