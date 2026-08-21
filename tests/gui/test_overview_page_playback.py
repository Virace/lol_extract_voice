"""总览页试听播放接线测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import Qt

import lol_audio_unpack.gui.view.overview_page as overview_page_module
from lol_audio_unpack.app.artifacts import AudioIndexProgress, AudioRef
from lol_audio_unpack.app.resource_pack import ResourcePackWadRef
from lol_audio_unpack.app.types import SourceMode
from lol_audio_unpack.gui.controllers.overview_preview import (
    ALL_AUDIO_PREVIEW_MODE,
    EVENT_PREVIEW_MODE,
    RAW_PREVIEW_MODE,
    AudioPreviewToggleResult,
    OverviewPreviewLoadResult,
)
from lol_audio_unpack.gui.shared_data import SharedDataPhase, SharedDataState
from lol_audio_unpack.gui.view.overview_page import OverviewPage


def _build_preview_load_result() -> OverviewPreviewLoadResult:
    """构造特殊内容预览链路共用的最小加载结果。"""
    return OverviewPreviewLoadResult(
        entity_id="66600",
        mapping_path=None,
        mapping_data=None,
        preview_content="",
        available_audio_ids=set(),
        group_label_map={},
        placeholder_message="尚未生成事件映射。",
    )


def test_overview_page_special_preview_uses_stable_state_key_and_champion_loader(qtbot) -> None:
    """特殊内容应以稳定 key 恢复目录状态，但仍按英雄 ID 加载预览。"""
    page = OverviewPage()
    qtbot.addWidget(page)
    calls: list[dict[str, object]] = []
    page._preview_playback_controller = SimpleNamespace(
        set_volume_percent=lambda _value: None,
        set_output_device_key=lambda _value: None,
        play=lambda **_kwargs: None,
        stop=lambda: None,
    )
    page._preview_controller = SimpleNamespace(
        load_preview=lambda **kwargs: calls.append(kwargs) or _build_preview_load_result(),
    )
    loader = object()
    page._ensure_loader = lambda: loader
    page.entityListPanel.resolve_row_payload = lambda _item: {
        "id": "66600",
        "key": "champion:66600",
        "name": "厄加特",
        "display_name": "末日人机 · 厄加特",
        "entity_type": "champions",
    }

    page._load_preview_for_item("special", object())

    assert page._current_preview_ids["special"] == "champion:66600"
    assert calls == [
        {
            "entity_type": "champions",
            "entity_id": "66600",
            "entity_name": "末日人机 · 厄加特",
            "loader": loader,
        }
    ]


def test_overview_page_schedules_resource_pack_scan_without_calling_discovery_on_ui_thread(qtbot, monkeypatch) -> None:
    """selected-WAD discovery 必须先交给线程池，不能在按钮处理期间执行。"""
    page = OverviewPage()
    qtbot.addWidget(page)
    context = SimpleNamespace()
    ref = ResourcePackWadRef("Game/DATA/FINAL/Legacy.wad.client", size=12, mtime_ns=34)
    scheduled = []
    app_calls = []
    page._app_context = context
    monkeypatch.setattr(
        overview_page_module,
        "QThreadPool",
        SimpleNamespace(globalInstance=lambda: SimpleNamespace(start=scheduled.append)),
    )

    class _FakeApp:
        def __init__(self, app_context) -> None:
            app_calls.append(app_context)

        def discover_resource_packs(self, _options):
            return object()

    monkeypatch.setattr(overview_page_module, "LolAudioUnpackApp", _FakeApp)

    page._start_resource_pack_scan((ref,))

    assert len(scheduled) == 1
    assert scheduled[0] is page._resource_pack_scan_worker
    assert app_calls == []


def test_overview_page_reports_audio_scan_and_defers_hidden_model_reset(qtbot) -> None:
    """事件页不扫描；全部音频报告进度且隐藏页不构建大模型。"""
    page = OverviewPage()
    qtbot.addWidget(page)
    page._sync_current_list_view = lambda: None
    page.show()
    scheduled = []
    expected_current = 15_360
    expected_total = 30_343
    event_ref = AudioRef(
        relative_path="SFX/1001.wem",
        path=Path("audios/map/SFX/1001.wem"),
        wem_id="1001",
        audio_type="SFX",
        sub_entity="22",
    )
    flat_ref = AudioRef(
        relative_path="MUSIC/2001.wem",
        path=Path("audios/map/MUSIC/2001.wem"),
        wem_id="2001",
        audio_type="MUSIC",
        sub_entity="22",
    )
    previous_ref = AudioRef(
        relative_path="SFX/9999.wem",
        path=Path("audios/previous/SFX/9999.wem"),
        wem_id="9999",
        audio_type="SFX",
        sub_entity="11",
    )
    page._preview_playback_controller = SimpleNamespace(
        set_volume_percent=lambda _value: None,
        set_output_device_key=lambda _value: None,
        play=lambda **_kwargs: None,
        stop=lambda: None,
    )
    page._preview_controller = SimpleNamespace(
        load_preview=lambda **_kwargs: OverviewPreviewLoadResult(
            entity_id="22",
            mapping_path=Path("map22.msgpack"),
            mapping_data={
                "map": {
                    "22": {
                        "events": {"SFX": {"evt": ["1001"]}},
                        "audioPaths": {"SFX": {"evt": [event_ref.relative_path]}},
                    }
                }
            },
            preview_content="{}",
            available_audio_ids={"1001"},
            group_label_map={"22": "云顶之弈"},
            event_audio_refs=(event_ref,),
            audio_refs_loaded=False,
            audio_roots=(Path("audios/map"),),
            default_preview_mode=EVENT_PREVIEW_MODE,
        )
    )
    page._app_context = SimpleNamespace()
    page._ensure_loader = object
    page.entityListPanel.resolve_row_payload = lambda _item: {"id": 22, "name": "云顶之弈"}
    page._audio_refs_pool = SimpleNamespace(start=scheduled.append)
    page.audioPreviewPanel.set_audio_refs((previous_ref,), summary_text="")
    page._audio_list_ready = True

    page._load_preview_for_item("maps", object())

    assert scheduled == []
    assert page.audio_list.model().rowCount() == 1
    assert page._current_event_audio_refs == (event_ref,)

    page.preview_mode_pivot.setCurrentItem(ALL_AUDIO_PREVIEW_MODE)

    assert len(scheduled) == 1
    assert scheduled[0] is page._audio_refs_worker
    assert page.audio_list.model().rowCount() == 0
    assert "正在发现全部音频" in page.audio_preview_summary_label.text()
    worker = scheduled[0]
    worker.signals.progress.emit(AudioIndexProgress(current=expected_current, total=expected_total))
    assert page.audioPreviewPanel.load_progress_bar.isHidden() is False
    assert page.audioPreviewPanel.load_progress_bar.value() == expected_current
    assert page.audioPreviewPanel.load_progress_bar.maximum() == expected_total
    assert "15,360 / 30,343（50%）" in page.audio_preview_summary_label.text()

    page.preview_mode_pivot.setCurrentItem(EVENT_PREVIEW_MODE)
    assert page.audioPreviewPanel.load_progress_bar.isHidden() is True
    page.preview_mode_pivot.setCurrentItem(ALL_AUDIO_PREVIEW_MODE)
    assert page.audioPreviewPanel.load_progress_bar.value() == expected_current

    page.hide()
    worker.signals.finished.emit((flat_ref,))
    assert page.audio_list.model().rowCount() == 0
    page.show()
    qtbot.waitUntil(lambda: page.audio_list.model().rowCount() == 1)
    assert "全部音频 1 个 WEM" in page.audio_preview_summary_label.text()

    resets: list[bool] = []
    page.audio_list.source_model.modelReset.connect(lambda: resets.append(True))
    page.preview_mode_pivot.setCurrentItem(EVENT_PREVIEW_MODE)
    page.preview_mode_pivot.setCurrentItem(ALL_AUDIO_PREVIEW_MODE)

    assert len(scheduled) == 1
    assert resets == []


def test_overview_page_reuses_current_preview_models_when_page_is_resynced(qtbot) -> None:
    """重新进入总览页时应复用当前实体模型，不能再次构建大型树。"""
    page = OverviewPage()
    qtbot.addWidget(page)
    calls: list[dict[str, object]] = []
    audio_ref = AudioRef(
        relative_path="SFX/1001.wem",
        path=Path("audios/map/SFX/1001.wem"),
        wem_id="1001",
        audio_type="SFX",
        sub_entity="22",
    )
    page._preview_playback_controller = SimpleNamespace(
        set_volume_percent=lambda _value: None,
        set_output_device_key=lambda _value: None,
        play=lambda **_kwargs: None,
        stop=lambda: None,
    )
    page._preview_controller = SimpleNamespace(
        load_preview=lambda **kwargs: (
            calls.append(kwargs)
            or OverviewPreviewLoadResult(
                entity_id="22",
                mapping_path=Path("map22.msgpack"),
                mapping_data={"map": {"22": {"events": {"SFX": {"evt": ["1001"]}}}}},
                preview_content="{}",
                available_audio_ids={"1001"},
                group_label_map={},
                audio_refs=(audio_ref,),
                default_preview_mode=EVENT_PREVIEW_MODE,
            )
        )
    )
    page._ensure_loader = object
    page.set_entity_data("maps", [{"id": 22, "name": "云顶之弈"}])
    page.nav_pivot.setCurrentItem("maps")
    current = page.entityListPanel.find_index_by_entity_id("maps", "22")
    page._current_entity_list().setCurrentIndex(current)
    page.preview_mode_pivot.setCurrentItem(ALL_AUDIO_PREVIEW_MODE)

    event_resets: list[bool] = []
    audio_resets: list[bool] = []
    page.audio_preview_tree.model().modelReset.connect(lambda: event_resets.append(True))
    page.audio_list.source_model.modelReset.connect(lambda: audio_resets.append(True))

    page._sync_current_list_view()

    assert len(calls) == 1
    assert event_resets == []
    assert audio_resets == []
    assert page.preview_mode_pivot.currentRouteKey() == ALL_AUDIO_PREVIEW_MODE
    assert page.audio_list.model().rowCount() == 1

    page.set_entity_data("maps", [{"id": 22, "name": "云顶之弈", "audio": "已存在"}])

    expected_reload_count = 2
    assert len(calls) == expected_reload_count


def test_overview_page_rejects_stale_all_audio_worker_result(qtbot) -> None:
    """旧实体的后台结果不得污染当前实体或当前上下文缓存。"""
    page = OverviewPage()
    qtbot.addWidget(page)
    page.show()
    scheduled = []
    first_ref = AudioRef(
        relative_path="SFX/1001.wem",
        path=Path("audios/map11/SFX/1001.wem"),
        wem_id="1001",
        audio_type="SFX",
        sub_entity="11",
    )
    second_ref = AudioRef(
        relative_path="SFX/2001.wem",
        path=Path("audios/map22/SFX/2001.wem"),
        wem_id="2001",
        audio_type="SFX",
        sub_entity="22",
    )
    current_row = {"id": 11, "name": "召唤师峡谷"}
    page._preview_playback_controller = SimpleNamespace(
        set_volume_percent=lambda _value: None,
        set_output_device_key=lambda _value: None,
        play=lambda **_kwargs: None,
        stop=lambda: None,
    )
    page._preview_controller = SimpleNamespace(
        load_preview=lambda **kwargs: OverviewPreviewLoadResult(
            entity_id=str(kwargs["entity_id"]),
            mapping_path=Path(f"map{kwargs['entity_id']}.msgpack"),
            mapping_data={"map": {str(kwargs["entity_id"]): {"events": {}}}},
            preview_content="{}",
            available_audio_ids=set(),
            group_label_map={},
            audio_refs_loaded=False,
            default_preview_mode=EVENT_PREVIEW_MODE,
        )
    )
    page._app_context = SimpleNamespace()
    page._ensure_loader = object
    page.entityListPanel.resolve_row_payload = lambda _item: dict(current_row)
    page._audio_refs_pool = SimpleNamespace(start=scheduled.append)

    page._load_preview_for_item("maps", object())
    page.preview_mode_pivot.setCurrentItem(ALL_AUDIO_PREVIEW_MODE)
    first_worker = scheduled[0]

    current_row.update(id=22, name="云顶之弈")
    page._load_preview_for_item("maps", object())
    page.preview_mode_pivot.setCurrentItem(ALL_AUDIO_PREVIEW_MODE)
    first_worker.signals.finished.emit((first_ref,))

    assert scheduled == [first_worker, page._audio_refs_worker]
    assert ("maps", "11") not in page._audio_refs_cache
    assert page._current_audio_refs == ()
    scheduled[-1].signals.finished.emit((second_ref,))
    assert page._current_audio_refs == (second_ref,)
    assert page.audio_list.model().rowCount() == 1


def test_overview_page_remote_special_tab_shows_local_only_notice(qtbot) -> None:
    """远端模式下特殊目录仍可浏览，但不能选择或发送。"""
    page = OverviewPage()
    qtbot.addWidget(page)
    page.set_entity_data(
        "special",
        [
            {
                "id": "66600",
                "key": "champion:66600",
                "name": "厄加特",
                "display_name": "末日人机 · 厄加特",
                "mode_key": "doom_bots",
                "audio": "未准备",
                "mapping": "未准备",
                "search_text": "末日人机 doom bots 厄加特 ruby_urgot 66600 champion:66600",
            }
        ],
    )
    page.nav_pivot.setCurrentItem("special")
    page.set_app_context(SimpleNamespace(config=SimpleNamespace(source_mode=SourceMode.REMOTE_SNAPSHOT)))

    item = (
        page.entityListPanel.current_list()
        .model()
        .index(
            0,
            0,
            page.entityListPanel.current_list().model().index(0, 0),
        )
    )

    assert page.entityListPanel.special_availability_label.isHidden() is False
    assert not bool(item.flags() & Qt.ItemFlag.ItemIsSelectable)
    assert page.subtitle_label.text() == "特殊内容仅支持本地客户端资源。"
    assert page.previewPanel.text_preview.toPlainText() == "特殊内容仅支持本地客户端资源。"

    page.nav_pivot.setCurrentItem("champions")

    assert page.entityListPanel.special_availability_label.isHidden() is True
    assert page.search_input.placeholderText() == "搜索英雄、别名或 ID"


def test_overview_page_updates_search_placeholder_per_entity_directory(qtbot) -> None:
    """一级目录切换应说明各自可搜索字段。"""
    page = OverviewPage()
    qtbot.addWidget(page)

    expected = {
        "champions": "搜索英雄、别名或 ID",
        "maps": "搜索地图、别名或 ID",
        "special": "搜索模式、英雄、别名或资源包",
    }
    for entity_type, placeholder in expected.items():
        page.nav_pivot.setCurrentItem(entity_type)
        assert page.search_input.placeholderText() == placeholder


def test_overview_page_special_catalog_empty_and_unprepared_states_are_explicit(qtbot) -> None:
    """本地目录应区分当前版本无 special 与需要更新实体数据。"""
    page = OverviewPage()
    qtbot.addWidget(page)
    page.set_shared_data_state(SharedDataState(SharedDataPhase.READY, 1, "local_path"))
    page.nav_pivot.setCurrentItem("special")
    page.set_app_context(SimpleNamespace(config=SimpleNamespace(source_mode=SourceMode.LOCAL_PATH)))

    assert page.previewPanel.text_preview.toPlainText() == "当前版本未发现特殊内容"

    page.set_entity_data(
        "special",
        [
            {
                "id": "66600",
                "key": "champion:66600",
                "name": "厄加特",
                "display_name": "末日人机 · 厄加特",
                "mode_key": "doom_bots",
                "audio": "未准备",
                "mapping": "未准备",
                "search_text": "末日人机 厄加特",
            }
        ],
    )

    assert (
        page.entityListPanel.special_availability_label.text()
        == "特殊内容资源尚未准备，需要更新实体数据后才能显示完整状态。"
    )
    assert page.entityListPanel.special_availability_label.isHidden() is False


def test_overview_page_clear_selection_resets_all_entity_directories(qtbot) -> None:
    """全局清空操作应同时清理英雄、地图和特殊内容状态。"""
    page = OverviewPage()
    qtbot.addWidget(page)
    page._selected_entity_ids = {
        "champions": {"1"},
        "maps": {"11"},
        "special": {"champion:66600"},
    }
    page._current_preview_ids = {
        "champions": "1",
        "maps": "11",
        "special": "champion:66600",
    }
    cleared: list[str] = []
    page.entityListPanel.clear_selection = cleared.append
    page._sync_current_list_view = lambda: None

    page._clear_selected_entities()

    assert page._selected_entity_ids == {"champions": set(), "maps": set(), "special": set()}
    assert page._current_preview_ids == {"champions": None, "maps": None, "special": None}
    assert cleared == ["champions", "maps", "special"]


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
