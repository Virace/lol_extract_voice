from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from lol_audio_unpack.gui.controllers.overview_preview import (
    AudioPreviewToggleResult,
    OverviewPreviewController,
    OverviewPreviewLoadResult,
)


def test_overview_preview_controller_returns_placeholder_when_loader_missing() -> None:
    controller = OverviewPreviewController()

    result = controller.load_preview(
        entity_type="champions",
        entity_id="1",
        entity_name="Annie",
        loader=None,
    )

    assert result == OverviewPreviewLoadResult(
        entity_id="1",
        mapping_path=None,
        mapping_data=None,
        preview_content="",
        available_audio_ids=set(),
        group_label_map={},
        placeholder_message="当前配置尚未完成初始化，暂时无法读取预览内容。",
    )


def test_overview_preview_controller_returns_placeholder_when_mapping_missing() -> None:
    controller = OverviewPreviewController()
    loader = SimpleNamespace(
        load_mapping_preview=lambda entity_type, entity_id: (None, None, ""),
    )

    result = controller.load_preview(
        entity_type="champions",
        entity_id="1",
        entity_name="Annie",
        loader=loader,
    )

    assert result.placeholder_message == "Annie 当前还没有映射文件。"
    assert result.mapping_path is None


def test_overview_preview_controller_builds_champion_group_labels() -> None:
    controller = OverviewPreviewController()
    mapping_path = Path("preview.msgpack")
    loader = SimpleNamespace(
        load_mapping_preview=lambda entity_type, entity_id: (
            mapping_path,
            {"skins": {"1000": {"events": {}}}},
            '{"skins": {"1000": {}}}',
        ),
        load_available_audio_ids=lambda entity_type, entity_id: {"1001", "1002"},
        data_reader=SimpleNamespace(
            get_champion=lambda champion_id: {
                "skins": [
                    {"id": 1000, "skinNames": {"zh_CN": "经典"}},
                    {"id": 2000, "name": "勇者"},
                ]
            }
        ),
    )

    result = controller.load_preview(
        entity_type="champions",
        entity_id="1",
        entity_name="Annie",
        loader=loader,
    )

    assert result.placeholder_message is None
    assert result.mapping_path == mapping_path
    assert result.available_audio_ids == {"1001", "1002"}
    assert result.group_label_map == {"1000": "经典", "2000": "勇者"}


def test_overview_preview_controller_toggle_clears_current_audio_request() -> None:
    controller = OverviewPreviewController()

    result = controller.resolve_audio_preview_toggle(
        requested_audio_id="1001",
        current_audio_id="1001",
        loader=None,
        current_entity_type="champions",
        current_entity_id="1",
    )

    assert result == AudioPreviewToggleResult(
        audio_id=None,
        audio_path=None,
        progress=0.0,
        is_playing=False,
        is_paused=False,
        warning_message=None,
    )


def test_overview_preview_controller_toggle_returns_warning_when_audio_missing() -> None:
    controller = OverviewPreviewController()
    loader = SimpleNamespace(
        resolve_audio_file_path=lambda entity_type, entity_id, audio_id: None,
    )

    result = controller.resolve_audio_preview_toggle(
        requested_audio_id="1001",
        current_audio_id=None,
        loader=loader,
        current_entity_type="champions",
        current_entity_id="1",
    )

    assert result == AudioPreviewToggleResult(
        audio_id=None,
        audio_path=None,
        progress=0.0,
        is_playing=False,
        is_paused=False,
        warning_message="当前实体未定位到音频 ID 1001 对应的 wem 文件。",
    )
