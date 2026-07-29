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


def test_overview_page_audio_menu_resolves_wem_without_toggling_playback(qtbot) -> None:
    page = OverviewPage()
    qtbot.addWidget(page)
    stopped: list[bool] = []
    page._preview_playback_controller = SimpleNamespace(
        set_volume_percent=lambda _value: None,
        set_output_device_key=lambda _value: None,
        play=lambda **_kwargs: None,
        stop=lambda: stopped.append(True),
    )
    page._loader = SimpleNamespace(
        resolve_audio_file_path=lambda entity_type, entity_id, audio_id: Path("1001.wem"),
    )
    page._current_preview_entity_type = "champions"
    page._current_preview_entity_id = "1"

    result = page._audio_menu_wem_path("1001")

    assert result == Path("1001.wem")
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
