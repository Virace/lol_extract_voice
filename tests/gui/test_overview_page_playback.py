"""总览页试听播放接线测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import lol_audio_unpack.gui.view.overview_page as overview_page_module
from lol_audio_unpack.app.artifacts import AudioRef
from lol_audio_unpack.gui.controllers.overview_preview import (
    ALL_AUDIO_PREVIEW_MODE,
    EVENT_PREVIEW_MODE,
    RAW_PREVIEW_MODE,
    AudioPreviewToggleResult,
    OverviewPreviewLoadResult,
)
from lol_audio_unpack.gui.view.overview_page import OverviewPage


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
            default_preview_mode=EVENT_PREVIEW_MODE,
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
            default_preview_mode=EVENT_PREVIEW_MODE,
            placeholder_message=None,
        )
    )
    page.entityListPanel.resolve_row_payload = lambda _item: {"id": 1, "name": "盖伦"}

    page._load_preview_for_item("champions", object())
    page.previewPanel.preview_search_input.setText("Baron")

    assert "匹配事件 1" in page.audio_preview_summary_label.text()
    assert "匹配 ID 2" in page.audio_preview_summary_label.text()


def test_overview_page_audio_menu_uses_exact_ref_without_toggling_playback(qtbot) -> None:
    page = OverviewPage()
    qtbot.addWidget(page)
    stopped: list[bool] = []
    page._preview_playback_controller = SimpleNamespace(
        set_volume_percent=lambda _value: None,
        set_output_device_key=lambda _value: None,
        play=lambda **_kwargs: None,
        stop=lambda: stopped.append(True),
    )
    audio_ref = AudioRef(
        relative_path="1000/VO/1001.wem",
        path=Path("1000/VO/1001.wem"),
        wem_id="1001",
        audio_type="VO",
        sub_entity="1000",
    )

    result = page._audio_menu_wem_path(audio_ref)

    assert result == audio_ref.path
    assert stopped == []


def test_overview_page_reveal_wav_reuses_existing_file(qtbot, tmp_path, monkeypatch) -> None:
    page = OverviewPage()
    qtbot.addWidget(page)
    wem_path = tmp_path / "audios" / "15.10" / "champions" / "1" / "VO" / "1001.wem"
    wav_path = tmp_path / "wavs" / "15.10" / "champions" / "1" / "VO" / "1001.wav"
    wav_path.parent.mkdir(parents=True)
    wav_path.write_bytes(b"RIFF....WAVE")
    page._app_context = SimpleNamespace(
        paths=SimpleNamespace(
            audio_path=tmp_path / "audios",
            wav_path=tmp_path / "wavs",
        )
    )
    page._loader = SimpleNamespace(data_reader=SimpleNamespace(version="15.10"))
    opened: list[Path] = []
    transcoded: list[tuple[Path, Path]] = []

    monkeypatch.setattr(page, "_reveal_file_path", lambda path: opened.append(Path(path)) or True)
    monkeypatch.setattr(
        overview_page_module,
        "transcode_wav",
        lambda source, target, *, wav_format: transcoded.append((Path(source), Path(target))) or Path(target),
        raising=False,
    )

    page._reveal_wav(wem_path)

    assert opened == [wav_path]
    assert transcoded == []


def test_overview_page_defaults_to_all_audio_without_mapping_and_uses_selected_exact_path(qtbot) -> None:
    page = OverviewPage()
    qtbot.addWidget(page)
    audio_ref = AudioRef(
        relative_path="1000/VO/1001.wem",
        path=Path("audios/entity/1000/VO/1001.wem"),
        wem_id="1001",
        audio_type="VO",
        sub_entity="1000",
    )
    page._preview_playback_controller = SimpleNamespace(
        set_volume_percent=lambda _value: None,
        set_output_device_key=lambda _value: None,
        play=lambda **_kwargs: None,
        stop=lambda: None,
    )
    page._preview_controller = SimpleNamespace(
        load_preview=lambda **_kwargs: OverviewPreviewLoadResult(
            entity_id="1",
            mapping_path=None,
            mapping_data=None,
            preview_content="尚未生成事件映射。",
            available_audio_ids={"1001"},
            group_label_map={},
            audio_refs=(audio_ref,),
            audio_roots=(Path("audios/entity/VO"), Path("audios/entity/SFX")),
            default_preview_mode=ALL_AUDIO_PREVIEW_MODE,
            mapping_notice="盖伦 尚未生成事件映射。",
        )
    )
    page.entityListPanel.resolve_row_payload = lambda _item: {"id": 1, "name": "盖伦"}

    page._load_preview_for_item("champions", object())

    assert page.preview_mode_pivot.currentRouteKey() == ALL_AUDIO_PREVIEW_MODE
    assert page.preview_stack.currentWidget() is page.audioPreviewPanel
    assert page.audioPreviewPanel.preview_stack.currentWidget() is page.audio_list
    assert "尚未生成事件映射" in page.audio_preview_summary_label.text()
    assert page.preview_path_edit.text().startswith("多个音频目录：")
    assert page.reveal_file_btn.isEnabled() is False
    page._on_audio_ref_selected(audio_ref)
    assert page.preview_path_edit.text() == str(audio_ref.path)
    assert page.reveal_file_btn.isEnabled() is True


def test_overview_page_mode_switch_keeps_event_summary_and_does_not_stop_playback(qtbot) -> None:
    page = OverviewPage()
    qtbot.addWidget(page)
    stopped: list[bool] = []
    audio_ref = AudioRef(
        relative_path="1000/VO/1001.wem",
        path=Path("audios/entity/1000/VO/1001.wem"),
        wem_id="1001",
        audio_type="VO",
        sub_entity="1000",
    )
    page._preview_playback_controller = SimpleNamespace(
        set_volume_percent=lambda _value: None,
        set_output_device_key=lambda _value: None,
        play=lambda **_kwargs: None,
        stop=lambda: stopped.append(True),
    )
    page._preview_controller = SimpleNamespace(
        load_preview=lambda **_kwargs: OverviewPreviewLoadResult(
            entity_id="1",
            mapping_path=Path("preview.msgpack"),
            mapping_data={"skins": {"1000": {"events": {"VO": {"evt": ["1001"]}}}}},
            preview_content="{}",
            available_audio_ids={"1001"},
            group_label_map={"1000": "经典"},
            audio_refs=(audio_ref,),
            default_preview_mode=EVENT_PREVIEW_MODE,
        )
    )
    page.entityListPanel.resolve_row_payload = lambda _item: {"id": 1, "name": "盖伦"}

    page._load_preview_for_item("champions", object())
    event_summary = page.audio_preview_summary_label.text()
    assert page.preview_path_edit.text() == "preview.msgpack"
    event_model = page.audio_preview_tree.model()
    event_index = event_model.index(0, 0)
    page.audio_preview_tree.setCurrentIndex(event_index)
    stopped.clear()

    page.preview_mode_pivot.setCurrentItem(ALL_AUDIO_PREVIEW_MODE)
    all_audio_summary = page.audio_preview_summary_label.text()
    all_audio_index = page.audio_list.model().index(0, 0)
    page.audio_list.setCurrentIndex(all_audio_index)
    page.preview_mode_pivot.setCurrentItem(RAW_PREVIEW_MODE)
    assert page.preview_path_edit.text() == "preview.msgpack"
    page.preview_mode_pivot.setCurrentItem(EVENT_PREVIEW_MODE)

    assert "分组 1" in event_summary
    assert "全部音频 1 个 WEM" in all_audio_summary
    assert page.audio_preview_summary_label.text() == event_summary
    assert page.audio_preview_tree.model() is event_model
    assert page.audio_preview_tree.currentIndex() == event_index
    page.preview_mode_pivot.setCurrentItem(ALL_AUDIO_PREVIEW_MODE)
    assert page.audio_list.currentIndex() == all_audio_index
    assert stopped == []


def test_overview_page_keeps_selected_audio_ref_per_preview_mode(qtbot) -> None:
    """切换模式时，全部音频必须恢复自己的精确路径选择。"""
    page = OverviewPage()
    qtbot.addWidget(page)
    first = AudioRef(
        relative_path="1000/VO/1001.wem",
        path=Path("audios/entity/1000/VO/1001.wem"),
        wem_id="1001",
        audio_type="VO",
        sub_entity="1000",
    )
    second = AudioRef(
        relative_path="1001/VO/1002.wem",
        path=Path("audios/entity/1001/VO/1002.wem"),
        wem_id="1002",
        audio_type="VO",
        sub_entity="1001",
    )
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
                        "events": {"VO": {"evt_first": ["1001"], "evt_second": ["1002"]}},
                        "audioPaths": {
                            "VO": {
                                "evt_first": [first.relative_path],
                                "evt_second": [second.relative_path],
                            }
                        },
                    }
                }
            },
            preview_content="{}",
            available_audio_ids={"1001", "1002"},
            group_label_map={"1000": "经典"},
            audio_refs=(first, second),
            default_preview_mode=EVENT_PREVIEW_MODE,
        )
    )
    page.entityListPanel.resolve_row_payload = lambda _item: {"id": 1, "name": "盖伦"}

    page._load_preview_for_item("champions", object())
    page.preview_mode_pivot.setCurrentItem(ALL_AUDIO_PREVIEW_MODE)
    first_index = page.audio_list.model().index(0, 0)
    page.audio_list.setCurrentIndex(first_index)
    assert page.preview_path_edit.text() == str(first.path)

    page.preview_mode_pivot.setCurrentItem(EVENT_PREVIEW_MODE)
    event_model = page.audio_preview_tree.model()
    event_root = event_model.index(0, 0)
    event_model.ensure_children_loaded(event_root)
    event_type = event_model.index(0, 0, event_root)
    event_model.ensure_children_loaded(event_type)
    second_event = event_model.index(1, 0, event_type)
    event_model.ensure_children_loaded(second_event)
    page.audio_preview_tree.setCurrentIndex(event_model.index(0, 0, second_event))
    assert page.preview_path_edit.text() == "preview.msgpack"

    page.preview_mode_pivot.setCurrentItem(ALL_AUDIO_PREVIEW_MODE)

    assert page.audio_list.currentIndex() == first_index
    assert page.preview_path_edit.text() == str(first.path)
    assert page._selected_audio_refs[EVENT_PREVIEW_MODE] == second
    assert page._selected_audio_refs[ALL_AUDIO_PREVIEW_MODE] == first


def test_overview_page_raw_mode_clears_visible_search_and_restores_mode_queries(qtbot) -> None:
    """raw 模式只清空显示值，事件与全部音频的查询缓存必须保留。"""
    page = OverviewPage()
    qtbot.addWidget(page)
    audio_ref = AudioRef(
        relative_path="1000/VO/1001.wem",
        path=Path("audios/entity/1000/VO/1001.wem"),
        wem_id="1001",
        audio_type="VO",
        sub_entity="1000",
    )
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
            mapping_data={"skins": {"1000": {"events": {"VO": {"event_name": ["1001"]}}}}},
            preview_content="{}",
            available_audio_ids={"1001"},
            group_label_map={"1000": "经典"},
            audio_refs=(audio_ref,),
            default_preview_mode=EVENT_PREVIEW_MODE,
        )
    )
    page.entityListPanel.resolve_row_payload = lambda _item: {"id": 1, "name": "盖伦"}

    page._load_preview_for_item("champions", object())
    search = page.previewPanel.preview_search_input
    search.setText("event")
    page.preview_mode_pivot.setCurrentItem(ALL_AUDIO_PREVIEW_MODE)
    search.setText("1001")
    page.preview_mode_pivot.setCurrentItem(RAW_PREVIEW_MODE)

    assert search.text() == ""
    assert search.isEnabled() is False
    assert search.placeholderText() == "原始数据暂不支持搜索"
    assert page._preview_search_keywords == {
        EVENT_PREVIEW_MODE: "event",
        ALL_AUDIO_PREVIEW_MODE: "1001",
    }

    page.preview_mode_pivot.setCurrentItem(EVENT_PREVIEW_MODE)
    assert search.text() == "event"
    page.preview_mode_pivot.setCurrentItem(RAW_PREVIEW_MODE)
    page.preview_mode_pivot.setCurrentItem(ALL_AUDIO_PREVIEW_MODE)
    assert search.text() == "1001"
