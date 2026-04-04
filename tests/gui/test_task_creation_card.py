"""执行中心任务创建卡片测试。"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from qfluentwidgets import GroupHeaderCardWidget

from lol_audio_unpack.gui.task_models import AppContextInputSnapshot
from lol_audio_unpack.gui.view.execution.task_creation_card import TaskCreationCard

EXPECTED_WAV_WORKERS = 6
EXPECTED_WAV_TIMEOUT = 9
EXPECTED_WAV_RETRIES = 4
EXPECTED_GAME_PATH = "game-root"
EXPECTED_OUTPUT_PATH = "output-root"
EXPECTED_GROUP_COUNT = 8
EXPECTED_ID_INPUT_WIDTH = 320
EXPECTED_SCOPE_TOGGLE_WIDTH = 180
EXPECTED_MAX_WORKERS_WIDTH = 120


@dataclass(slots=True)
class _FakeGuiConfig:
    """任务表单测试使用的最小 GUI 配置替身。"""

    extract_wav_enabled: bool = True
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


def test_task_creation_card_uses_group_header_card_widget(qtbot) -> None:
    """任务表单应基于 GroupHeaderCardWidget 承载全部参数行。"""
    panel = _build_panel(qtbot)

    assert isinstance(panel, GroupHeaderCardWidget)
    assert panel.groupCount() == EXPECTED_GROUP_COUNT


def test_task_creation_card_uses_gui_wav_defaults_for_draft(qtbot) -> None:
    """显式启用 WAV 时，任务草稿应携带默认转码参数。"""
    panel = _build_panel(qtbot)
    gui_config = _FakeGuiConfig()

    panel.apply_gui_config_defaults(gui_config)
    panel.apply_defaults()
    panel.wav_output_cb.setChecked(True)
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


def test_task_creation_card_keeps_wav_switch_disabled_by_default(qtbot) -> None:
    """执行中心即使读取到 CLI 的 WAV 配置，默认也不应自动勾选 WAV。"""
    panel = _build_panel(qtbot)

    panel.apply_gui_config_defaults(_FakeGuiConfig(extract_wav_enabled=True))
    panel.apply_defaults()
    panel.sync_state_from_widgets()

    draft = panel.build_task_draft(gui_config=_FakeGuiConfig(extract_wav_enabled=True))

    assert panel.wav_output_cb.isChecked() is False
    assert draft.task_params.wav_enabled is False


def test_task_creation_card_drops_wav_when_extract_is_disabled(qtbot) -> None:
    """未勾选音频解包时，不应继续携带 WAV 相关参数。"""
    panel = _build_panel(qtbot)
    gui_config = _FakeGuiConfig()

    panel.apply_gui_config_defaults(gui_config)
    panel.apply_defaults()
    panel.extract_task_cb.setChecked(False)
    panel.sync_state_from_widgets()

    draft = panel.build_task_draft(gui_config=gui_config)

    assert draft.task_params.run_extract is False
    assert draft.task_params.wav_enabled is False


def test_task_creation_card_restore_button_resets_custom_inputs_to_defaults(qtbot) -> None:
    """恢复按钮应把自定义输入恢复到默认值，并放在创建任务按钮左侧。"""
    panel = _build_panel(qtbot)

    panel.champion_ids_input.setText("1,103")
    panel.map_ids_input.setText("11")
    panel.vo_filter.setCurrentItem("ALL")
    panel.max_workers_combo.setCurrentText("16")
    panel.bp_voice_cb.setChecked(False)
    panel.force_update_cb.setChecked(True)
    panel.integrate_data_cb.setChecked(False)
    panel.wav_output_cb.setChecked(True)
    panel.wav_format_combo.setCurrentText("float")
    panel.sync_state_from_widgets()

    qtbot.mouseClick(panel.restore_defaults_btn, Qt.MouseButton.LeftButton)

    assert panel.bottom_toolbar_layout.indexOf(panel.restore_defaults_btn) < panel.bottom_toolbar_layout.indexOf(
        panel.create_task_btn
    )
    assert panel.champion_ids_input.text() == ""
    assert panel.map_ids_input.text() == ""
    assert panel.vo_filter.currentRouteKey() == "VO"
    assert panel.max_workers_combo.currentText() == "4"
    assert panel.bp_voice_cb.isChecked() is True
    assert panel.force_update_cb.isChecked() is False
    assert panel.integrate_data_cb.isChecked() is True
    assert panel.wav_output_cb.isChecked() is False
    assert panel.wav_format_combo.currentText() == "pcm16"


def test_task_creation_card_uses_balanced_control_widths(qtbot) -> None:
    """英雄/地图输入宽度应统一，右侧状态控件应更紧凑。"""
    panel = _build_panel(qtbot)

    assert panel.champion_ids_input.minimumWidth() == EXPECTED_ID_INPUT_WIDTH
    assert panel.map_ids_input.minimumWidth() == EXPECTED_ID_INPUT_WIDTH
    assert panel.champion_ids_input.maximumWidth() == EXPECTED_ID_INPUT_WIDTH
    assert panel.map_ids_input.maximumWidth() == EXPECTED_ID_INPUT_WIDTH
    assert panel.vo_filter.maximumWidth() == EXPECTED_SCOPE_TOGGLE_WIDTH
    assert panel.max_workers_combo.maximumWidth() == EXPECTED_MAX_WORKERS_WIDTH
