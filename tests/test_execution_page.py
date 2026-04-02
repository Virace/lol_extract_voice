"""执行中心页面交互回归测试。"""

from __future__ import annotations

from lol_audio_unpack.gui.view.execution_page import ExecutionPage
from lol_audio_unpack.gui.view.setting_page import SettingPage

EXPECTED_WAV_WORKERS = 8
EXPECTED_WAV_TIMEOUT = 15
EXPECTED_WAV_RETRIES = 5


def test_execution_page_initializes_with_queue_placeholder(qtbot) -> None:
    page = ExecutionPage()
    qtbot.addWidget(page)

    assert page.draft_list.count() == 1
    placeholder = page.draft_list.item(0)
    assert placeholder is not None
    assert placeholder.text() == "当前任务队列为空。"


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

    execution_page.advancedPanel.wav_output_cb.setChecked(True)
    execution_page.advancedPanel.wav_format_combo.setCurrentText("float")
    execution_page.taskBuilderPanel.sync_state_from_widgets()

    draft = execution_page.taskBuilderPanel.build_task_draft(gui_config=execution_page.gui_config)

    assert draft.task_params.wav_enabled is True
    assert draft.task_params.wav_workers == EXPECTED_WAV_WORKERS
    assert draft.task_params.wav_timeout == EXPECTED_WAV_TIMEOUT
    assert draft.task_params.wav_retries == EXPECTED_WAV_RETRIES
    assert draft.task_params.wav_format == "float"


def test_execution_page_hides_cli_copy_entrypoint(qtbot) -> None:
    """执行中心不应再向普通用户暴露 CLI 复制入口。"""
    _setting_page, execution_page = _build_linked_pages(qtbot)

    assert not hasattr(execution_page, "copy_cli_btn")
    assert not hasattr(execution_page.taskBuilderPanel, "copy_cli_btn")
