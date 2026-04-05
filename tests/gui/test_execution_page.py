"""执行中心页面交互回归测试。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor

from lol_audio_unpack.gui.view.execution_page import ExecutionPage
from lol_audio_unpack.gui.view.setting_page import SettingPage

EXPECTED_WAV_WORKERS = 8
EXPECTED_WAV_TIMEOUT = 15
EXPECTED_WAV_RETRIES = 5
EXPECTED_TASK_BUILDER_MIN_HEIGHT = 300
EXPECTED_GROUP_COUNT = 8
EXPECTED_CONTENT_TEXT_LIGHT = QColor(96, 96, 96)
EXPECTED_CONTENT_TEXT_DARK = QColor(206, 206, 206)


def test_execution_page_uses_single_task_creation_card(qtbot) -> None:
    """执行中心页面不再显示任务队列 UI，只保留单一卡片。"""
    page = ExecutionPage()
    qtbot.addWidget(page)

    assert not hasattr(page, "draft_list")
    assert not hasattr(page, "taskQueuePanel")
    assert page.advancedPanel is page.taskBuilderPanel
    assert page.taskBuilderPanel.groupCount() == EXPECTED_GROUP_COUNT


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
    assert draft.task_params.wav_retries == EXPECTED_WAV_RETRIES
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


def test_execution_page_hides_cli_copy_entrypoint(qtbot) -> None:
    """执行中心不应再向普通用户暴露 CLI 复制入口。"""
    _setting_page, execution_page = _build_linked_pages(qtbot)

    assert not hasattr(execution_page, "copy_cli_btn")
    assert not hasattr(execution_page.taskBuilderPanel, "copy_cli_btn")


def test_execution_page_embeds_advanced_panel_into_task_builder(qtbot) -> None:
    """顶部自定义输入应直接由任务配置卡承载。"""
    page = ExecutionPage()
    qtbot.addWidget(page)
    page.resize(1120, 840)
    page.show()
    qtbot.waitUntil(page.taskBuilderPanel.isVisible)

    assert page.advancedPanel is page.taskBuilderPanel
    assert page.taskBuilderPanel.groupCount() == EXPECTED_GROUP_COUNT


def test_execution_page_cards_keep_visible_height_in_default_layout(qtbot, tmp_path: Path) -> None:
    """当前数据量下，顶部设置卡与底部单行卡不应额外出现滚动。"""
    page = ExecutionPage()
    qtbot.addWidget(page)
    page.resize(1120, 840)
    page.show()
    qtbot.waitUntil(lambda: page.isVisible() and page.taskBuilderPanel.isVisible())

    screenshot_path = tmp_path / "execution-page-default.png"
    page.grab().save(str(screenshot_path))

    assert screenshot_path.exists()
    assert page.verticalScrollBar().maximum() == 0
    assert page.taskBuilderPanel.height() >= EXPECTED_TASK_BUILDER_MIN_HEIGHT


def test_execution_page_global_progress_state_hidden_by_default(qtbot) -> None:
    """默认页面不应主动显示全局进度条。"""
    page = ExecutionPage()
    qtbot.addWidget(page)

    state = page.current_global_progress_state()

    assert state.visible is False


def test_execution_page_mock_queue_updates_global_progress_state(qtbot) -> None:
    """队列进入运行态后，应产出可供主窗口使用的全局进度条状态。"""
    page = ExecutionPage()
    qtbot.addWidget(page)

    page._debug_fill_mock_queue(3)
    state = page.current_global_progress_state()

    assert state.visible is True
    assert state.title_text != ""
    assert state.detail_text != ""
    assert state.rate_text == ""
    assert state.status_text != ""


def test_execution_page_subtitle_uses_setting_card_content_tone(qtbot) -> None:
    """页头副标题应直接复用 Fluent 次级文案色。"""
    page = ExecutionPage()
    qtbot.addWidget(page)

    assert page.subtitle_label.lightColor == EXPECTED_CONTENT_TEXT_LIGHT
    assert page.subtitle_label.darkColor == EXPECTED_CONTENT_TEXT_DARK
