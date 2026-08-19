"""resource-pack 解包消费者的定向测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from lol_audio_unpack.app.path_layout import format_entity_folder_name, get_entity_path_component
from lol_audio_unpack.app.resource_pack import build_resource_pack_key
from lol_audio_unpack.model import AudioBank, AudioEntityData
from lol_audio_unpack.model.binding import BankBinding, BindingDiagnostics, BindingRole, BindingStatus, Completeness
from lol_audio_unpack.unpack import batch as unpack_batch
from lol_audio_unpack.unpack import entity as unpack_entity


class _FakeWad:
    """返回一个可供 BNK 边界解析的固定容器。"""

    @staticmethod
    def extract(_paths, *, raw: bool):  # noqa: ANN001
        """返回单个固定容器数据。"""
        assert raw is True
        return [b"bank"]


class _FakeWem:
    """模拟一个可持久化的 WEM 条目。"""

    id = 101
    data = b"wem"

    @staticmethod
    def save_file(path: Path) -> None:
        """写入固定 WEM 字节。"""
        path.write_bytes(b"wem")


class _FakeBnk:
    """模拟 BNK 容器的单 WEM 提取。"""

    def __init__(self, raw_data: bytes) -> None:
        """验证解包输入保持原始容器字节。"""
        assert raw_data == b"bank"

    @staticmethod
    def extract_files() -> list[_FakeWem]:
        """返回固定 WEM。"""
        return [_FakeWem()]


def _build_entity(key: str) -> AudioEntityData:
    """创建使用单个 resolved binding 的 resource-pack 实体。"""
    binding = BankBinding(
        category="MODE_TFT_NPC_ElderDragon_SFX",
        path="assets/elder_dragon_audio.bnk",
        normalized_path="assets/elder_dragon_audio.bnk",
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
        resource_banks=(AudioBank(sub_id=key, audio_type="SFX", binding=binding),),
        binding_diagnostics=BindingDiagnostics(completeness=Completeness.COMPLETE),
    )


def test_bound_resource_pack_extracts_to_isolated_safe_output_and_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """resource-pack binding 解包应保留 key 于报告、但所有路径使用 safe component。"""
    key = build_resource_pack_key("TFTCommon.wad.client", "MODE_TFT_NPC_ElderDragon_SFX")
    entity = _build_entity(key)
    game_path = tmp_path / "game"
    source_wad = game_path / "Game" / "DATA" / "FINAL" / "TFTCommon.wad.client"
    source_wad.parent.mkdir(parents=True)
    source_wad.write_bytes(b"wad")
    ctx = SimpleNamespace(
        game_path=game_path,
        audio_path=tmp_path / "audios",
        report_path=tmp_path / "reports",
        game_region="zh_CN",
        include_types=("SFX",),
        exclude_types=(),
        group_by_type=True,
        config=SimpleNamespace(dev_mode=False),
    )
    reader = SimpleNamespace(version="16.16")
    monkeypatch.setattr(unpack_entity, "_get_wad_instance", lambda *_args, **_kwargs: _FakeWad())
    monkeypatch.setattr(unpack_entity, "BNK", _FakeBnk)

    unpack_entity.unpack_entity(entity, reader, ctx=ctx)

    component = get_entity_path_component("resource_pack", key)
    entity_folder = format_entity_folder_name(component, entity.entity_alias, entity.entity_name)
    wem_path = ctx.audio_path / reader.version / "SFX" / "resource_packs" / entity_folder / "101.wem"
    report_path = ctx.report_path / reader.version / "resource_packs" / f"_{component}_metadata.yaml"
    assert wem_path.read_bytes() == b"wem"
    assert report_path.is_file()
    assert ":" not in report_path.name


def test_resource_pack_batch_dispatches_string_task(monkeypatch: pytest.MonkeyPatch) -> None:
    """批处理必须把 resource-pack key 交给专用 string consumer。"""
    key = build_resource_pack_key("TFTCommon.wad.client", "MODE_TFT_NPC_ElderDragon_SFX")
    calls: list[str] = []
    reader = SimpleNamespace(version="16.16", write_unknown_categories=lambda: None)
    ctx = SimpleNamespace(config=SimpleNamespace(dev_mode=False))
    monkeypatch.setattr(unpack_batch, "unpack_resource_pack", lambda value, *_args, **_kwargs: calls.append(value))

    unpack_batch.unpack_resource_packs(reader, [key], max_workers=1, ctx=ctx)

    assert calls == [key]
