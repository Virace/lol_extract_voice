"""`AudioEntityData` 统一实体构造入口测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from lol_audio_unpack.app.types import SourceMode
from lol_audio_unpack.model import AudioEntityData
from lol_audio_unpack.model.binding import (
    BankBinding,
    BindingDiagnostics,
    BindingRole,
    BindingStatus,
    Completeness,
    ResourceBindings,
)


def test_from_entity_dispatches_to_champion_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    captured: dict[str, object] = {}

    def _fake_from_champion(cls, entity_id, reader, include_events=False, *, ctx):  # noqa: ANN001
        captured.update(
            entity_id=entity_id,
            reader=reader,
            include_events=include_events,
            ctx=ctx,
        )
        return sentinel

    monkeypatch.setattr(AudioEntityData, "from_champion", classmethod(_fake_from_champion))

    reader = object()
    ctx = object()
    result = AudioEntityData.from_entity(
        "champion",
        1,
        reader,
        include_events=True,
        ctx=ctx,
    )

    assert result is sentinel
    assert captured == {
        "entity_id": 1,
        "reader": reader,
        "include_events": True,
        "ctx": ctx,
    }


def test_from_entity_dispatches_to_map_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    captured: dict[str, object] = {}

    def _fake_from_map(cls, entity_id, reader, include_events=False, *, ctx):  # noqa: ANN001
        captured.update(
            entity_id=entity_id,
            reader=reader,
            include_events=include_events,
            ctx=ctx,
        )
        return sentinel

    monkeypatch.setattr(AudioEntityData, "from_map", classmethod(_fake_from_map))

    reader = object()
    ctx = object()
    result = AudioEntityData.from_entity(
        "map",
        11,
        reader,
        ctx=ctx,
    )

    assert result is sentinel
    assert captured == {
        "entity_id": 11,
        "reader": reader,
        "include_events": False,
        "ctx": ctx,
    }


def test_from_entity_rejects_unknown_type() -> None:
    with pytest.raises(ValueError, match="未知的实体类型: npc"):
        AudioEntityData.from_entity(
            "npc",
            1,
            SimpleNamespace(),
            ctx=SimpleNamespace(game_region="zh_CN"),
        )


def test_local_factory_uses_typed_v2_bindings_without_loading_events() -> None:
    """local 消费投影应保留 P1 binding，且 extract 构造不读取 events。"""
    binding = BankBinding(
        category="CHARACTER_VO",
        path="assets/voice_audio.bnk",
        normalized_path="",
        kind="BNK",
        wad="Game/DATA/FINAL/Champions/FiddleSticks.zh_CN.wad.client",
        entry_hash="0000000000000001",
        source_bin="data/characters/jade_fiddlesticks/skins/skin301.bin",
        role=BindingRole.LOCALIZED,
        status=BindingStatus.RESOLVED,
        sub_entity="6000901",
    )
    resources = ResourceBindings(
        entity_type="champion",
        entity_id="60009",
        bin_bindings=(),
        bank_bindings=(binding,),
        diagnostics=BindingDiagnostics(completeness=Completeness.COMPLETE),
    )
    reader = SimpleNamespace(
        get_champion=lambda _id: {
            "id": 60009,
            "alias": "Jade_Fiddlesticks",
            "names": {"zh_CN": "玉剑费德提克"},
            "titles": {"zh_CN": "恐惧使者"},
            "skins": [{"id": 6000901, "isBase": False, "skinNames": {"zh_CN": "玉剑"}}],
            "wad": {"root": "Game/DATA/FINAL/Champions/FiddleSticks.wad.client"},
        },
        get_champion_resource_bindings=lambda _id: resources,
        get_champion_banks=lambda _id: pytest.fail("local v2 不应回退到旧 banks projection"),
        get_champion_events=lambda _id: pytest.fail("extract 构造不应读取 events"),
        get_audio_type=lambda _category: "VO",
    )
    ctx = SimpleNamespace(
        config=SimpleNamespace(source_mode=SourceMode.LOCAL_PATH),
        game_region="zh_CN",
    )

    entity = AudioEntityData.from_champion(60009, reader, ctx=ctx)

    assert entity.resource_banks[0].binding is binding
    assert entity.resource_banks[0].sub_id == "6000901"
    assert entity.resource_banks[0].audio_type == "VO"
    assert entity.binding_diagnostics is resources.diagnostics
    assert entity.events is None


def test_remote_factory_keeps_v1_projection_without_local_binding_api() -> None:
    """remote v1 不应实例化 local binding 读取或合成伪 projection。"""
    reader = SimpleNamespace(
        get_champion=lambda _id: {
            "id": 1,
            "alias": "Annie",
            "names": {"zh_CN": "安妮"},
            "titles": {},
            "skins": [{"id": 1000, "isBase": True, "skinNames": {"zh_CN": "基础皮肤"}}],
            "wad": {"root": "Game/root.wad.client"},
        },
        get_champion_banks=lambda _id: {"skins": {"1000": {"CHARACTER_VO": [["voice.bnk"]]}}},
        get_champion_resource_bindings=lambda _id: pytest.fail("remote v1 不应读取 local binding"),
    )
    ctx = SimpleNamespace(
        config=SimpleNamespace(source_mode=SourceMode.REMOTE_SNAPSHOT),
        game_region="zh_CN",
    )

    entity = AudioEntityData.from_champion(1, reader, ctx=ctx)

    assert entity.resource_banks == ()
    assert entity.binding_diagnostics is None
    assert entity.sub_entities["1000"]["categories"] == {"CHARACTER_VO": [["voice.bnk"]]}
