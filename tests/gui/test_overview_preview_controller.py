from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from lol_audio_unpack.app.artifacts import AudioRef
from lol_audio_unpack.app.resource_pack import build_resource_pack_key
from lol_audio_unpack.gui.controllers.overview_preview import (
    ALL_AUDIO_PREVIEW_MODE,
    EVENT_PREVIEW_MODE,
    AudioPreviewToggleResult,
    OverviewPreviewController,
    OverviewPreviewLoadResult,
)
from lol_audio_unpack.gui.service.data_loader import _normalize_integrated_mapping_data


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


def test_overview_preview_controller_keeps_audio_refs_when_mapping_missing() -> None:
    controller = OverviewPreviewController()
    audio_ref = AudioRef(
        relative_path="1000/VO/1001.wem",
        path=Path("1000/VO/1001.wem"),
        wem_id="1001",
        audio_type="VO",
        sub_entity="1000",
    )
    loader = SimpleNamespace(
        load_mapping_preview=lambda entity_type, entity_id: (None, None, ""),
        load_audio_refs=lambda entity_type, entity_id: (audio_ref,),
        load_audio_roots=lambda entity_type, entity_id, **_kwargs: (Path("audios/entity"),),
    )

    result = controller.load_preview(
        entity_type="champions",
        entity_id="1",
        entity_name="Annie",
        loader=loader,
    )

    assert result.placeholder_message is None
    assert result.mapping_path is None
    assert result.audio_refs == (audio_ref,)
    assert result.default_preview_mode == ALL_AUDIO_PREVIEW_MODE
    assert result.mapping_notice == "Annie 尚未生成事件映射。"


def test_resource_pack_preview_keeps_flat_audio_and_hides_stable_key_from_group_label() -> None:
    """资源包缺 mapping 时仍可试听，存在 mapping 时首层显示 catalog 名称。"""
    key = build_resource_pack_key("Legacy.wad.client", "MODE_LEGACY")
    audio_ref = AudioRef(
        relative_path="SFX/1001.wem",
        path=Path("resource_packs/legacy/SFX/1001.wem"),
        wem_id="1001",
        audio_type="SFX",
        sub_entity=key,
    )
    loader = SimpleNamespace(
        load_mapping_preview=lambda *_args: (None, None, ""),
        load_audio_refs=lambda *_args: (audio_ref,),
        load_audio_roots=lambda *_args, **_kwargs: (Path("resource_packs/legacy"),),
    )
    controller = OverviewPreviewController()

    result = controller.load_preview(
        entity_type="resource_packs",
        entity_id=key,
        entity_name="历史资源包 · Legacy",
        loader=loader,
    )

    assert result.default_preview_mode == ALL_AUDIO_PREVIEW_MODE
    assert result.audio_refs == (audio_ref,)
    assert result.group_label_map == {key: "历史资源包 · Legacy"}


def test_normalize_integrated_resource_pack_mapping_preserves_audio_paths() -> None:
    """资源包整合 mapping 必须保留事件到精确 WEM 路径的关联。"""
    key = build_resource_pack_key("Legacy.wad.client", "MODE_LEGACY")

    result = _normalize_integrated_mapping_data(
        {
            "data": {
                "resourcePack": {
                    "key": key,
                    "events": {"SFX": {"banks": [], "mapping": {"evt": ["1001"]}}},
                    "audioPaths": {"SFX": {"evt": ["SFX/1001.wem"]}},
                }
            }
        },
        entity_type="resource_packs",
        entity_id=key,
    )

    assert result is not None
    assert result["resourcePacks"] == {
        key: {
            "events": {"SFX": {"evt": ["1001"]}},
            "audioPaths": {"SFX": {"evt": ["SFX/1001.wem"]}},
        }
    }


def test_overview_preview_controller_builds_champion_group_labels() -> None:
    controller = OverviewPreviewController()
    mapping_path = Path("preview.msgpack")
    audio_refs = (
        AudioRef("1000/VO/1001.wem", Path("1000/VO/1001.wem"), "1001", "VO", "1000"),
        AudioRef("1000/VO/1002.wem", Path("1000/VO/1002.wem"), "1002", "VO", "1000"),
    )
    loader = SimpleNamespace(
        load_mapping_preview=lambda entity_type, entity_id: (
            mapping_path,
            {"skins": {"1000": {"events": {}}}},
            '{"skins": {"1000": {}}}',
        ),
        load_audio_refs=lambda entity_type, entity_id: audio_refs,
        load_audio_roots=lambda entity_type, entity_id, **_kwargs: (),
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
    assert result.default_preview_mode == EVENT_PREVIEW_MODE


def test_overview_preview_controller_toggle_clears_same_exact_audio_request() -> None:
    controller = OverviewPreviewController()
    audio_ref = AudioRef(
        relative_path="1000/VO/1001.wem",
        path=Path("1000/VO/1001.wem"),
        wem_id="1001",
        audio_type="VO",
        sub_entity="1000",
    )

    result = controller.resolve_audio_preview_toggle(
        requested_audio=audio_ref,
        current_audio_path=audio_ref.path,
    )

    assert result == AudioPreviewToggleResult(
        audio_id=None,
        audio_path=None,
        progress=0.0,
        is_playing=False,
        is_paused=False,
        warning_message=None,
    )


def test_overview_preview_controller_toggle_uses_requested_exact_audio_path() -> None:
    controller = OverviewPreviewController()
    audio_ref = AudioRef(
        relative_path="1001/VO/1001.wem",
        path=Path("1001/VO/1001.wem"),
        wem_id="1001",
        audio_type="VO",
        sub_entity="1001",
    )

    result = controller.resolve_audio_preview_toggle(
        requested_audio=audio_ref,
        current_audio_path=None,
    )

    assert result == AudioPreviewToggleResult(
        audio_id="1001",
        audio_path=audio_ref.path,
        progress=0.0,
        is_playing=False,
        is_paused=True,
        warning_message=None,
    )


def test_normalize_integrated_champion_mapping_preserves_audio_paths() -> None:
    result = _normalize_integrated_mapping_data(
        {
            "data": {
                "championId": 1,
                "skins": [
                    {
                        "id": 1000,
                        "events": {"VO": {"banks": [], "mapping": {"evt": ["1001"]}}},
                        "audioPaths": {"VO": {"evt": ["1000/VO/1001.wem"]}},
                    }
                ],
            }
        },
        entity_type="champions",
        entity_id="1",
    )

    assert result == {
        "metadata": {},
        "championId": 1,
        "alias": "",
        "skins": {
            "1000": {
                "events": {"VO": {"evt": ["1001"]}},
                "audioPaths": {"VO": {"evt": ["1000/VO/1001.wem"]}},
            }
        },
    }


def test_normalize_integrated_map_mapping_preserves_audio_paths() -> None:
    result = _normalize_integrated_mapping_data(
        {
            "data": {
                "mapId": 11,
                "name": "召唤师峡谷",
                "map": {
                    "events": {"SFX": {"banks": [], "mapping": {"evt": ["2001"]}}},
                    "audioPaths": {"SFX": {"evt": ["SFX/2001.wem"]}},
                },
            }
        },
        entity_type="maps",
        entity_id="11",
    )

    assert result is not None
    assert result["map"] == {
        "11": {
            "events": {"SFX": {"evt": ["2001"]}},
            "audioPaths": {"SFX": {"evt": ["SFX/2001.wem"]}},
        }
    }
