"""总览页试听播放接线测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import lol_audio_unpack.gui.view.overview_page as overview_page_module
from lol_audio_unpack.gui.controllers.overview_preview import (
    AudioPreviewToggleResult,
    OverviewPreviewLoadResult,
)
from lol_audio_unpack.gui.view.overview_page import OverviewPage


def test_overview_page_preview_audio_settings_forward_to_playback_controller(qtbot) -> None:
    page = OverviewPage()
    qtbot.addWidget(page)
    volumes: list[int] = []
    devices: list[str] = []
    page._preview_playback_controller = SimpleNamespace(
        set_volume_percent=volumes.append,
        set_output_device_key=devices.append,
        play=lambda **_kwargs: None,
        stop=lambda: None,
    )

    page.set_preview_audio_volume(35)
    page.set_preview_audio_output_device("device:test-output")

    assert volumes == [35]
    assert devices == ["device:test-output"]


def test_overview_page_toggle_audio_preview_starts_preview_playback(qtbot) -> None:
    page = OverviewPage()
    qtbot.addWidget(page)
    started: list[tuple[str, Path]] = []
    stopped: list[bool] = []
    page._preview_playback_controller = SimpleNamespace(
        set_volume_percent=lambda _value: None,
        set_output_device_key=lambda _value: None,
        play=lambda *, audio_id, audio_path: started.append((audio_id, Path(audio_path))),
        stop=lambda: stopped.append(True),
    )
    page._preview_controller = SimpleNamespace(
        resolve_audio_preview_toggle=lambda **_kwargs: AudioPreviewToggleResult(
            audio_id="1001",
            audio_path=Path("preview.wem"),
            progress=0.0,
            is_playing=False,
            is_paused=False,
            warning_message=None,
        )
    )
    page._loader = object()
    page._current_preview_entity_type = "champions"
    page._current_preview_entity_id = "1"

    page._on_audio_preview_toggle_requested("1001")

    assert started == [("1001", Path("preview.wem"))]
    assert stopped == []


def test_overview_page_show_placeholder_stops_preview_playback(qtbot) -> None:
    page = OverviewPage()
    qtbot.addWidget(page)
    stopped: list[bool] = []
    page._preview_playback_controller = SimpleNamespace(
        set_volume_percent=lambda _value: None,
        set_output_device_key=lambda _value: None,
        play=lambda **_kwargs: None,
        stop=lambda: stopped.append(True),
    )

    page._show_placeholder("请选择左侧实体。")

    assert stopped == [True]


def test_overview_page_load_preview_restores_event_view_when_event_tab_is_selected(qtbot) -> None:
    page = OverviewPage()
    qtbot.addWidget(page)
    page._preview_playback_controller = SimpleNamespace(
        set_volume_percent=lambda _value: None,
        set_output_device_key=lambda _value: None,
        play=lambda **_kwargs: None,
        stop=lambda: None,
    )
    page._preview_controller = SimpleNamespace(
        load_preview=lambda **_kwargs: OverviewPreviewLoadResult(
            entity_id="1",
            mapping_path=Path("preview.msgpack"),
            mapping_data={"skins": {"1000": {"events": {}}}},
            preview_content='{"skins": {"1000": {"events": {}}}}',
            available_audio_ids={"1001"},
            group_label_map={"1000": "经典"},
            placeholder_message=None,
        )
    )
    page.entityListPanel.resolve_row_payload = lambda _item: {"id": 1, "name": "盖伦"}
    page.previewPanel.show_placeholder("请选择左侧实体。")
    page.preview_mode_pivot.setCurrentItem("audio")

    page._load_preview_for_item("champions", object())

    assert page.preview_stack.currentWidget() is page.audioPreviewPanel


def test_overview_page_preview_search_filters_event_tree(qtbot) -> None:
    page = OverviewPage()
    qtbot.addWidget(page)
    page._preview_playback_controller = SimpleNamespace(
        set_volume_percent=lambda _value: None,
        set_output_device_key=lambda _value: None,
        play=lambda **_kwargs: None,
        stop=lambda: None,
    )
    page._preview_controller = SimpleNamespace(
        load_preview=lambda **_kwargs: OverviewPreviewLoadResult(
            entity_id="1",
            mapping_path=Path("preview.msgpack"),
            mapping_data={
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
            },
            preview_content='{"skins": {"1000": {"events": {}}}}',
            available_audio_ids={"261984525", "520515702", "888888888"},
            group_label_map={"1000": "经典"},
            placeholder_message=None,
        )
    )
    page.entityListPanel.resolve_row_payload = lambda _item: {"id": 1, "name": "盖伦"}

    page._load_preview_for_item("champions", object())
    page.previewPanel.preview_search_input.setText("Baron")

    assert "匹配事件 1" in page.audio_preview_summary_label.text()
    assert "匹配 ID 2" in page.audio_preview_summary_label.text()


def test_overview_page_logs_preview_modifiers_after_loading_preview(qtbot) -> None:
    page = OverviewPage()
    qtbot.addWidget(page)
    page._preview_playback_controller = SimpleNamespace(
        set_volume_percent=lambda _value: None,
        set_output_device_key=lambda _value: None,
        play=lambda **_kwargs: None,
        stop=lambda: None,
    )
    page._preview_controller = SimpleNamespace(
        load_preview=lambda **_kwargs: OverviewPreviewLoadResult(
            entity_id="12",
            mapping_path=Path("preview.msgpack"),
            mapping_data={
                "map": {
                    "12": {
                        "events": {
                            "NPC_Map12_VO": {},
                            "MUS_Map12_FirstBlood": {},
                            "ENV_Map12_SFX": {},
                        }
                    }
                }
            },
            preview_content='{"map": {"12": {"events": {}}}}',
            available_audio_ids=set(),
            group_label_map={"12": "极地大乱斗"},
            placeholder_message=None,
        )
    )
    page.entityListPanel.resolve_row_payload = lambda _item: {"id": 12, "name": "嚎哭深渊"}

    records: list[tuple] = []
    original_debug = overview_page_module.logger.debug
    overview_page_module.logger.debug = lambda *args: records.append(args)
    try:
        page._load_preview_for_item("maps", object())
    finally:
        overview_page_module.logger.debug = original_debug

    assert len(records) == 1
    template, entity_type, entity_id, prefixes, suffixes, audio_types = records[0]
    assert template.startswith("[总览预览]")
    assert entity_type == "maps"
    assert entity_id == 12
    assert prefixes == ["ENV", "MUS", "NPC"]
    assert suffixes == ["FirstBlood", "SFX", "VO"]
    assert audio_types == ["ENV_Map12_SFX", "MUS_Map12_FirstBlood", "NPC_Map12_VO"]
