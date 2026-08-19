"""resource-pack mapping 消费者的定向测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import lol_audio_unpack.mapping.entity as mapping_entity
import lol_audio_unpack.mapping.session as mapping_session
from lol_audio_unpack.app.path_layout import format_entity_folder_name, get_entity_path_component
from lol_audio_unpack.app.resource_pack import build_resource_pack_key
from lol_audio_unpack.mapping import batch as mapping_batch
from lol_audio_unpack.model import AudioBank, AudioEntityData
from lol_audio_unpack.model.binding import BankBinding, BindingDiagnostics, BindingRole, BindingStatus, Completeness


def _build_entity(key: str) -> AudioEntityData:
    """创建带一个 resolved events binding 的 resource-pack 实体。"""
    category = "MODE_TFT_NPC_ElderDragon_SFX"
    binding = BankBinding(
        category=category,
        path="assets/elder_dragon_events.bnk",
        normalized_path="assets/elder_dragon_events.bnk",
        kind="BNK",
        wad="Game/DATA/FINAL/TFTCommon.wad.client",
        entry_hash="0000000000000001",
        source_bin="resource_pack/0000000000000002.bin",
        role=BindingRole.ROOT,
        status=BindingStatus.RESOLVED,
    )
    return AudioEntityData(
        entity_id=key,
        entity_name="MODE TFT NPC ElderDragon SFX",
        entity_alias="mode_tft_npc_elderdragon_sfx",
        entity_title=None,
        entity_type="resource_pack",
        sub_entities={key: {"name": "MODE TFT NPC ElderDragon SFX", "categories": {}}},
        wad_root="Game/DATA/FINAL/TFTCommon.wad.client",
        events={key: {"events": {}}},
        resource_banks=(AudioBank(sub_id=key, audio_type="SFX", binding=binding),),
        binding_diagnostics=BindingDiagnostics(completeness=Completeness.COMPLETE),
    )


def _build_ctx(tmp_path: Path) -> SimpleNamespace:
    """提供 bound mapping 所需的最小本地上下文。"""
    return SimpleNamespace(
        game_path=tmp_path / "game",
        cache_path=tmp_path / "cache",
        hash_path=tmp_path / "hashes",
        paths=SimpleNamespace(audio_path=tmp_path / "audios"),
        config=SimpleNamespace(group_by_type=True, include_types=("SFX",), dev_mode=False),
    )


def _write_flat_audio(ctx: SimpleNamespace, entity: AudioEntityData, version: str) -> None:
    """创建一个已 extract 的 flat WEM，供 mapping coverage 使用。"""
    component = get_entity_path_component(entity.entity_type, entity.entity_id)
    folder = format_entity_folder_name(component, entity.entity_alias, entity.entity_name)
    wem_path = ctx.paths.audio_path / version / "SFX" / "resource_packs" / folder / "101.wem"
    wem_path.parent.mkdir(parents=True)
    wem_path.write_bytes(b"wem")


def test_resource_pack_mapping_keeps_flat_audio_when_events_missing_and_writes_safe_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """缺少 events 只形成诊断；raw mapping 仍隔离写入安全路径。"""
    key = build_resource_pack_key("TFTCommon.wad.client", "MODE_TFT_NPC_ElderDragon_SFX")
    entity = _build_entity(key)
    ctx = _build_ctx(tmp_path)
    reader = SimpleNamespace(version="16.16", get_languages=lambda: ["zh_CN"])
    written: list[tuple[dict[str, object], Path]] = []
    _write_flat_audio(ctx, entity, reader.version)
    monkeypatch.setattr(
        mapping_entity.AudioEntityData,
        "from_entity",
        classmethod(lambda cls, *_args, **_kwargs: entity),
    )
    monkeypatch.setattr(
        mapping_entity,
        "write_data",
        lambda payload, path, **_kwargs: written.append((payload, path)),
    )

    result = mapping_entity.build_resource_pack(key, reader, wwiser_manager=object(), ctx=ctx)

    component = get_entity_path_component("resource_pack", key)
    assert result["resourcePackKey"] == key
    assert result["resourcePacks"] == {}
    assert result["mappingDiagnostics"]["missingEventCategories"] == [
        {"subEntity": key, "category": "MODE_TFT_NPC_ElderDragon_SFX"}
    ]
    assert result["mappingDiagnostics"]["unmappedWemCount"] == 1
    assert written[0][1] == ctx.hash_path / reader.version / "resource_packs" / component
    assert ":" not in written[0][1].name


def test_resource_pack_raw_mapping_attaches_audio_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """resource-pack raw mapping 必须以完整 key 索引事件和已 extract 的平铺 WEM 路径。"""
    key = build_resource_pack_key("TFTCommon.wad.client", "MODE_TFT_NPC_ElderDragon_SFX")
    entity = _build_entity(key)
    category = "MODE_TFT_NPC_ElderDragon_SFX"
    entity.events = {key: {"events": {category: ["evt"]}}}
    ctx = _build_ctx(tmp_path)
    source_wad = ctx.game_path / "Game" / "DATA" / "FINAL" / "TFTCommon.wad.client"
    source_wad.parent.mkdir(parents=True)
    source_wad.write_bytes(b"wad")
    reader = SimpleNamespace(version="16.16", get_languages=lambda: ["zh_CN"])
    _write_flat_audio(ctx, entity, reader.version)

    class _FakeWad:
        """返回一个固定 events BNK。"""

        @staticmethod
        def extract(_paths, *, raw: bool):  # noqa: ANN001
            """返回 raw BNK bytes。"""
            assert raw is True
            return [b"bnk"]

    class _FakeMapping:
        """提供一个固定事件映射。"""

        forward_mapping = {"evt": [101]}

        def merge_with(self, _other: object) -> None:
            """单 binding 不需要合并。"""

    class _FakeMapper:
        """避免测试上游 HIRC 解析。"""

        def __init__(self, _events: list[str], _hirc: object) -> None:
            """接收 mapping 输入。"""

        @staticmethod
        def build_mapping() -> _FakeMapping:
            """返回固定映射。"""
            return _FakeMapping()

    monkeypatch.setattr(
        mapping_entity.AudioEntityData,
        "from_entity",
        classmethod(lambda cls, *_args, **_kwargs: entity),
    )
    monkeypatch.setattr(mapping_session, "_get_wad", lambda *_args, **_kwargs: _FakeWad())
    monkeypatch.setattr(mapping_session, "_get_cached_hirc", lambda **_kwargs: object())
    monkeypatch.setattr(mapping_entity, "AudioEventMapper", _FakeMapper)
    monkeypatch.setattr(mapping_entity, "write_data", lambda *_args, **_kwargs: None)

    result = mapping_entity.build_resource_pack(key, reader, wwiser_manager=object(), ctx=ctx)

    assert result["resourcePacks"][key]["audioPaths"] == {category: {"evt": ["SFX/101.wem"]}}
    assert result["mappingDiagnostics"]["completeness"] == "complete"


def test_resource_pack_integrated_mapping_has_readable_stable_structure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """integrated mapping 不得按 map 降级，需保留 resource-pack key 与 namespace。"""
    key = build_resource_pack_key("TFTCommon.wad.client", "MODE_TFT_NPC_ElderDragon_SFX")
    entity = _build_entity(key)
    ctx = _build_ctx(tmp_path)
    reader = SimpleNamespace(
        version="16.16",
        get_languages=lambda: ["zh_CN"],
        get_resource_pack_banks=lambda _key, **_kwargs: {
            "resourcePack": {
                "key": key,
                "namespace": "MODE_TFT_NPC_ElderDragon_SFX",
                "wad": "Game/DATA/FINAL/TFTCommon.wad.client",
            },
            "banks": {"MODE_TFT_NPC_ElderDragon_SFX": [["assets/elder_dragon_events.bnk"]]},
        },
    )
    written: list[tuple[dict[str, object], Path]] = []
    monkeypatch.setattr(
        mapping_entity.AudioEntityData,
        "from_entity",
        classmethod(lambda cls, *_args, **_kwargs: entity),
    )
    monkeypatch.setattr(
        mapping_entity,
        "write_data",
        lambda payload, path, **_kwargs: written.append((payload, path)),
    )

    result = mapping_entity.build_resource_pack(
        key,
        reader,
        wwiser_manager=object(),
        integrate_data=True,
        ctx=ctx,
    )

    component = get_entity_path_component("resource_pack", key)
    assert result["data"]["resourcePack"] == {
        "key": key,
        "name": "MODE TFT NPC ElderDragon SFX",
        "namespace": "MODE_TFT_NPC_ElderDragon_SFX",
        "wad": {"root": "Game/DATA/FINAL/TFTCommon.wad.client"},
    }
    assert written[0][1] == ctx.hash_path / reader.version / "integrated" / "resource_packs" / component


def test_resource_pack_mapping_batch_dispatches_string_task(monkeypatch: pytest.MonkeyPatch) -> None:
    """mapping batch 必须将 resource-pack string key 发送到专用 builder。"""
    key = build_resource_pack_key("TFTCommon.wad.client", "MODE_TFT_NPC_ElderDragon_SFX")
    calls: list[str] = []
    reader = SimpleNamespace(version="16.16")
    ctx = SimpleNamespace(config=SimpleNamespace(dev_mode=False))
    monkeypatch.setattr(mapping_batch, "build_resource_pack", lambda value, *_args, **_kwargs: calls.append(value))
    monkeypatch.setattr(mapping_batch.mapping_session, "describe_hirc_backend", lambda _ctx: "native")
    monkeypatch.setattr(mapping_batch.mapping_session, "_create_wwiser_manager", lambda _ctx: object())

    mapping_batch.build_resource_packs(reader, [key], max_workers=1, ctx=ctx)

    assert calls == [key]
