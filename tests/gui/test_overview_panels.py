"""总览页子面板的最小回归测试。"""

from __future__ import annotations

from contextlib import contextmanager

from PySide6.QtGui import QColor, QPalette
from qfluentwidgets import qconfig

from lol_audio_unpack.gui.components.overview_entity_list import _build_overview_interaction_colors
from lol_audio_unpack.gui.components.overview_status_badge import (
    resolve_status_pill_chrome_colors,
    resolve_status_pill_segment_colors,
)
from lol_audio_unpack.gui.controllers.contracts import OverviewSelectionSyncRequest
from lol_audio_unpack.gui.theme import apply_accent_preset, apply_shell_mode, get_accent_preset
from lol_audio_unpack.gui.view.overview.audio_preview_panel import OverviewAudioPreviewPanel
from lol_audio_unpack.gui.view.overview.entity_list_panel import OverviewEntityListPanel
from lol_audio_unpack.gui.view.overview.preview_panel import OverviewPreviewPanel

ALPHA_OPAQUE = 255


@contextmanager
def _restore_theme_state():
    """在测试结束后恢复 qconfig 主题状态。"""
    previous_theme = qconfig.themeMode.value
    previous_color = qconfig.themeColor.value
    try:
        yield
    finally:
        qconfig.set(qconfig.themeMode, previous_theme)
        qconfig.set(qconfig.themeColor, previous_color)


def test_overview_entity_list_panel_switches_current_entity_type(qtbot) -> None:
    panel = OverviewEntityListPanel()
    qtbot.addWidget(panel)

    assert panel.current_entity_type() == "champions"
    assert panel.current_list() is panel.entity_lists["champions"]

    panel.set_current_entity_type("maps")
    panel.set_selection_actions_enabled(True)

    assert panel.current_entity_type() == "maps"
    assert panel.current_list() is panel.entity_lists["maps"]
    assert panel.clear_selection_btn.isEnabled() is True
    assert panel.sync_selection_btn.isEnabled() is True
    panel.set_selection_counts(champion_count=2, map_count=1)
    assert panel.selection_status_label.text() == "已选 2 个英雄，1 张地图。"


def test_overview_entity_list_panel_filters_and_finds_entity_ids(qtbot) -> None:
    panel = OverviewEntityListPanel()
    qtbot.addWidget(panel)
    panel.set_rows(
        "champions",
        [
            {"id": 1, "name": "Annie", "alias": "annie"},
            {"id": 103, "name": "Ahri", "alias": "ahri"},
        ],
    )

    visible_count = panel.apply_keyword_and_restore(
        entity_type="champions",
        keyword="ann",
        selected_ids={"1"},
        current_entity_id="1",
    )
    index = panel.find_index_by_entity_id("champions", "1")

    assert visible_count == 1
    assert index.isValid() is True
    assert panel.current_list().selected_entity_ids() == {"1"}
    assert panel.selected_entity_ids("champions") == {"1"}
    assert panel.resolve_row_payload(index) == {"id": 1, "name": "Annie", "alias": "annie"}


def test_overview_entity_list_panel_can_clear_selection_state(qtbot) -> None:
    panel = OverviewEntityListPanel()
    qtbot.addWidget(panel)
    panel.set_rows(
        "champions",
        [
            {"id": 1, "name": "Annie", "alias": "annie"},
            {"id": 103, "name": "Ahri", "alias": "ahri"},
        ],
    )
    panel.apply_keyword_and_restore(
        entity_type="champions",
        keyword="",
        selected_ids={"1"},
        current_entity_id="1",
    )

    panel.clear_selection("champions")

    assert panel.selected_entity_ids("champions") == set()
    assert panel.current_list().currentIndex().isValid() is False


def test_overview_entity_list_panel_can_build_selection_sync_request(qtbot) -> None:
    panel = OverviewEntityListPanel()
    qtbot.addWidget(panel)

    payload = panel.build_selection_sync_request(
        selected_champion_ids={"103", "1"},
        selected_map_ids={"11"},
    )

    assert payload == OverviewSelectionSyncRequest(
        source="overview_selection",
        champion_ids=(1, 103),
        map_ids=(11,),
        summary="已选择 2 个英雄、1 张地图，请前往执行中心继续创建任务。",
    )


def test_overview_interaction_colors_use_accent_preset_tone() -> None:
    """总览列表选中 accent 应来自固定 preset tone。"""
    with _restore_theme_state():
        apply_shell_mode("Light")
        apply_accent_preset("green")

        _hover_background, _selection_background, selection_accent = _build_overview_interaction_colors()
        expected_accent = get_accent_preset("green").scale.color(700)

        assert selection_accent == expected_accent


def test_overview_status_pill_uses_active_preset_colors() -> None:
    """实体胶囊存在态应跟随当前 accent preset。"""
    palette = QPalette()

    with _restore_theme_state():
        apply_shell_mode("Light")
        apply_accent_preset("blue")

        audio_fill, audio_text = resolve_status_pill_segment_colors("A", "已存在", palette)
        mapping_fill, mapping_text = resolve_status_pill_segment_colors("M", "已存在", palette)

        assert audio_fill == get_accent_preset("blue").scale.color(500)
        assert mapping_fill == QColor("#4E69CC")
        assert audio_text == QColor("#FFFFFF")
        assert mapping_text == QColor("#FFFFFF")

    with _restore_theme_state():
        apply_shell_mode("Dark")
        apply_accent_preset("purple")

        audio_fill, audio_text = resolve_status_pill_segment_colors("A", "已存在", palette)
        mapping_fill, mapping_text = resolve_status_pill_segment_colors("M", "已存在", palette)

        assert audio_fill == get_accent_preset("purple").scale.color(300)
        assert mapping_fill == QColor("#A99BF4")
        assert audio_text == QColor("#111111")
        assert mapping_text == QColor("#111111")

    with _restore_theme_state():
        apply_shell_mode("Light")
        apply_accent_preset("purple")

        _audio_fill, _audio_text = resolve_status_pill_segment_colors("A", "已存在", palette)
        mapping_fill, _mapping_text = resolve_status_pill_segment_colors("M", "已存在", palette)

        assert mapping_fill == QColor("#6E58C9")

    with _restore_theme_state():
        apply_shell_mode("Dark")
        apply_accent_preset("green")

        audio_fill, mapping_fill = (
            resolve_status_pill_segment_colors("A", "已存在", palette)[0],
            resolve_status_pill_segment_colors("M", "已存在", palette)[0],
        )

        assert audio_fill == get_accent_preset("green").scale.color(300)
        assert mapping_fill == QColor("#93AC72")


def test_overview_status_pill_uses_transparent_fill_for_missing_state() -> None:
    """实体胶囊缺失态应统一退回透明底。"""
    palette = QPalette()

    with _restore_theme_state():
        apply_shell_mode("Dark")
        apply_accent_preset("orange")

        audio_fill, audio_text = resolve_status_pill_segment_colors("A", "未存在", palette)
        mapping_fill, mapping_text = resolve_status_pill_segment_colors("M", "未存在", palette)

        assert audio_fill.alpha() == 0
        assert mapping_fill.alpha() == 0
        assert 0 < audio_text.alpha() < ALPHA_OPAQUE
        assert 0 < mapping_text.alpha() < ALPHA_OPAQUE


def test_overview_status_pill_uses_brighter_chrome_on_dark_palette() -> None:
    """深色主题下胶囊描边和接缝线应明显提亮。"""
    palette = QPalette()

    with _restore_theme_state():
        apply_shell_mode("Light")
        light_seam, light_outline = resolve_status_pill_chrome_colors(palette)

    with _restore_theme_state():
        apply_shell_mode("Dark")
        dark_seam, dark_outline = resolve_status_pill_chrome_colors(palette)

    assert dark_seam.alpha() > light_seam.alpha()
    assert dark_outline.alpha() > light_outline.alpha()


def test_overview_preview_panel_show_placeholder_clears_preview_state(qtbot) -> None:
    panel = OverviewPreviewPanel(audio_summary_placeholder="这里会显示当前实体的事件分组。")
    qtbot.addWidget(panel)

    panel.set_preview_path("mapping.msgpack")
    panel.reveal_file_btn.setEnabled(True)
    panel.show_placeholder("请选择左侧实体。")

    assert panel.preview_path_edit.text() == ""
    assert panel.preview_path_edit.toolTip() == ""
    assert panel.text_preview.toPlainText() == "请选择左侧实体。"
    assert panel.preview_stack.currentWidget() is panel.text_preview
    assert panel.reveal_file_btn.isEnabled() is False


def test_overview_preview_panel_set_preview_path_updates_text_and_tooltip(qtbot) -> None:
    panel = OverviewPreviewPanel(audio_summary_placeholder="这里会显示当前实体的事件分组。")
    qtbot.addWidget(panel)

    panel.set_preview_path("mapping.msgpack")

    assert panel.preview_path_edit.text() == "mapping.msgpack"
    assert panel.preview_path_edit.toolTip() == "mapping.msgpack"


def test_overview_audio_preview_panel_can_reset_summary(qtbot) -> None:
    panel = OverviewAudioPreviewPanel(summary_placeholder="等待事件数据。")
    qtbot.addWidget(panel)

    panel.set_summary_text("分组 1 · 类型 2 · 事件 3")
    panel.reset_summary()

    assert panel.summary_label.text() == "等待事件数据。"


def test_overview_audio_preview_panel_can_set_preview_data_and_playback_state(qtbot) -> None:
    panel = OverviewAudioPreviewPanel(summary_placeholder="等待事件数据。")
    qtbot.addWidget(panel)

    panel.set_preview_data(
        mapping_data={"skins": {"1000": {"events": {}}}},
        available_audio_ids={"1001"},
        group_label_map={"1000": "经典"},
        summary_text="分组 1 · 类型 0 · 事件 0",
    )
    panel.set_playback_state("1001", progress=0.25, is_playing=False, is_paused=True)

    assert panel.summary_label.text() == "分组 1 · 类型 0 · 事件 0"
