"""总览页子面板的最小回归测试。"""

from __future__ import annotations

from lol_audio_unpack.gui.components.preview_tree import (
    extract_preview_modifiers,
    extract_tree_groups,
    filter_preview_mapping_data,
)
from lol_audio_unpack.gui.controllers.contracts import OverviewSelectionSyncRequest
from lol_audio_unpack.gui.view.overview.audio_preview_panel import OverviewAudioPreviewPanel
from lol_audio_unpack.gui.view.overview.entity_list_panel import OverviewEntityListPanel
from lol_audio_unpack.gui.view.overview.preview_panel import OverviewPreviewPanel

MATCHED_AUDIO_IDS = 2


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
    assert panel.preview_stack.currentWidget() is panel.placeholder_panel
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


def test_overview_audio_preview_panel_expands_single_root_by_default(qtbot) -> None:
    panel = OverviewAudioPreviewPanel(summary_placeholder="等待事件数据。")
    qtbot.addWidget(panel)

    panel.set_preview_data(
        mapping_data={"map": {"0": {"events": {"NPC_Map0_VO": {"Play_map0_intro": ["1001"]}}}}},
        available_audio_ids={"1001"},
        group_label_map={"0": "常规"},
        summary_text="分组 1 · 类型 1 · 事件 1",
    )

    root_index = panel.audio_preview_tree.model().index(0, 0)

    assert panel.audio_preview_tree.isExpanded(root_index) is True


def test_overview_audio_preview_panel_keeps_multiple_roots_collapsed_by_default(qtbot) -> None:
    panel = OverviewAudioPreviewPanel(summary_placeholder="等待事件数据。")
    qtbot.addWidget(panel)

    panel.set_preview_data(
        mapping_data={
            "skins": {
                "1000": {"events": {"XinZhao_Base_VO": {"Play_base_intro": ["1001"]}}},
                "1001": {"events": {"XinZhao_Skin_VO": {"Play_skin_intro": ["1002"]}}},
            }
        },
        available_audio_ids={"1001", "1002"},
        group_label_map={"1000": "经典", "1001": "屠龙勇士"},
        summary_text="分组 2 · 类型 2 · 事件 2",
    )

    first_root_index = panel.audio_preview_tree.model().index(0, 0)
    second_root_index = panel.audio_preview_tree.model().index(1, 0)

    assert panel.audio_preview_tree.isExpanded(first_root_index) is False
    assert panel.audio_preview_tree.isExpanded(second_root_index) is False


def test_filter_preview_mapping_data_keeps_full_event_when_event_name_matches() -> None:
    mapping_data = {
        "skins": {
            "1000": {
                "events": {
                    "XinZhao_Base_VO": {
                        "Play_vo_XinZhao_Attack2DBaron": ["261984525", "520515702"],
                        "Play_vo_XinZhao_Attack2DDragon": ["888888888"],
                    }
                }
            }
        }
    }

    result = filter_preview_mapping_data(mapping_data, "baron")
    groups = extract_tree_groups(result.mapping_data)
    events = groups["1000"]["events"]["XinZhao_Base_VO"]

    assert result.is_active is True
    assert result.matched_event_count == 1
    assert result.matched_audio_id_count == MATCHED_AUDIO_IDS
    assert events == {"Play_vo_XinZhao_Attack2DBaron": ["261984525", "520515702"]}


def test_filter_preview_mapping_data_keeps_only_matching_audio_id_when_id_matches() -> None:
    mapping_data = {
        "skins": {
            "1000": {
                "events": {
                    "XinZhao_Base_VO": {
                        "Play_vo_XinZhao_Attack2DBaron": ["261984525", "520515702"],
                        "Play_vo_XinZhao_Attack2DDragon": ["888888888"],
                    }
                }
            }
        }
    }

    result = filter_preview_mapping_data(mapping_data, "2619")
    groups = extract_tree_groups(result.mapping_data)
    events = groups["1000"]["events"]["XinZhao_Base_VO"]

    assert result.is_active is True
    assert result.matched_event_count == 1
    assert result.matched_audio_id_count == 1
    assert events == {"Play_vo_XinZhao_Attack2DBaron": ["261984525"]}


def test_extract_preview_modifiers_collects_prefixes_and_suffixes() -> None:
    mapping_data = {
        "map": {
            "12": {
                "events": {
                    "NPC_Map12_VO": {},
                    "MUS_Map12_FirstBlood": {},
                    "ITEMS_Global": {},
                    "HUD_Global": {},
                    "ENV_Map12_SFX": {},
                }
            }
        }
    }

    result = extract_preview_modifiers(mapping_data)

    assert result.prefixes == ("ENV", "HUD", "ITEMS", "MUS", "NPC")
    assert result.suffixes == ("FirstBlood", "Global", "SFX", "VO")
    assert result.audio_types == (
        "ENV_Map12_SFX",
        "HUD_Global",
        "ITEMS_Global",
        "MUS_Map12_FirstBlood",
        "NPC_Map12_VO",
    )


def test_filter_preview_mapping_data_supports_suffix_modifier_scope() -> None:
    mapping_data = {
        "skins": {
            "1000": {
                "events": {
                    "XinZhao_Base_VO": {
                        "Play_vo_XinZhao_Attack2DBaron": ["261984525", "520515702"],
                    },
                    "XinZhao_Base_SFX": {
                        "Play_sfx_XinZhao_Attack2DBaron": ["777777777"],
                    },
                }
            }
        }
    }

    result = filter_preview_mapping_data(mapping_data, "vo:baron")
    groups = extract_tree_groups(result.mapping_data)
    events = groups["1000"]["events"]

    assert result.is_active is True
    assert result.matched_event_count == 1
    assert result.matched_audio_id_count == MATCHED_AUDIO_IDS
    assert events == {
        "XinZhao_Base_VO": {
            "Play_vo_XinZhao_Attack2DBaron": ["261984525", "520515702"],
        }
    }


def test_filter_preview_mapping_data_supports_prefix_modifier_scope_without_keyword() -> None:
    mapping_data = {
        "map": {
            "12": {
                "events": {
                    "ITEMS_Global": {
                        "Play_items_shop": ["8053", "8054"],
                    },
                    "HUD_Global": {
                        "Play_hud_ping": ["9001"],
                    },
                }
            }
        }
    }

    result = filter_preview_mapping_data(mapping_data, "items:")
    groups = extract_tree_groups(result.mapping_data)
    events = groups["12"]["events"]

    assert result.is_active is True
    assert result.matched_event_count == 1
    assert result.matched_audio_id_count == MATCHED_AUDIO_IDS
    assert events == {
        "ITEMS_Global": {
            "Play_items_shop": ["8053", "8054"],
        }
    }
