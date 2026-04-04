"""总览页子面板的最小回归测试。"""

from __future__ import annotations

from lol_audio_unpack.gui.controllers.contracts import OverviewSelectionSyncRequest
from lol_audio_unpack.gui.view.overview.audio_preview_panel import OverviewAudioPreviewPanel
from lol_audio_unpack.gui.view.overview.entity_list_panel import OverviewEntityListPanel
from lol_audio_unpack.gui.view.overview.preview_panel import OverviewPreviewPanel


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
