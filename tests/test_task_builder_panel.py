"""执行中心任务表单中的参数测试。"""

from __future__ import annotations

from dataclasses import dataclass

from lol_audio_unpack.gui.task_models import AppContextInputSnapshot
from lol_audio_unpack.gui.view.execution.advanced_input_panel import AdvancedInputPanel
from lol_audio_unpack.gui.view.execution.task_builder_panel import TaskBuilderPanel

EXPECTED_WAV_WORKERS = 6
EXPECTED_WAV_TIMEOUT = 9
EXPECTED_WAV_RETRIES = 4
EXPECTED_GAME_PATH = "game-root"
EXPECTED_OUTPUT_PATH = "output-root"


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


def _build_panel(qtbot) -> tuple[TaskBuilderPanel, AdvancedInputPanel]:
    """创建绑定完成的任务表单与高级输入面板。"""
    panel = TaskBuilderPanel()
    advanced_panel = AdvancedInputPanel()
    panel.bind_advanced_panel(advanced_panel)
    qtbot.addWidget(panel)
    qtbot.addWidget(advanced_panel)
    return panel, advanced_panel


def test_task_builder_panel_uses_gui_wav_defaults_for_draft(qtbot) -> None:
    """启用 WAV 时，任务草稿应携带默认转码参数。"""
    panel, _advanced_panel = _build_panel(qtbot)
    gui_config = _FakeGuiConfig()

    panel.apply_gui_config_defaults(gui_config)
    panel.apply_defaults()
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


def test_task_builder_panel_drops_wav_when_extract_is_disabled(qtbot) -> None:
    """未勾选音频解包时，不应继续携带 WAV 相关参数。"""
    panel, _advanced_panel = _build_panel(qtbot)
    gui_config = _FakeGuiConfig()

    panel.apply_gui_config_defaults(gui_config)
    panel.apply_defaults()
    panel.extract_task_cb.setChecked(False)
    panel.sync_state_from_widgets()

    draft = panel.build_task_draft(gui_config=gui_config)

    assert draft.task_params.run_extract is False
    assert draft.task_params.wav_enabled is False
