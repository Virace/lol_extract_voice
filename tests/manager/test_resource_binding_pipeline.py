"""local v2 resource binding 处理链与 remote 兼容合同测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from lol_audio_unpack.app.types import SourceMode
from lol_audio_unpack.manager import bin_source as bin_source_module
from lol_audio_unpack.manager import champion_bin_processor as champion_module
from lol_audio_unpack.manager import data_reader as data_reader_module
from lol_audio_unpack.manager import map_bin_processor as map_module
from lol_audio_unpack.manager.bin_source import BinBatch, LoadedBin
from lol_audio_unpack.manager.data_reader import DataReader
from lol_audio_unpack.manager.errors import ResourceSchemaMismatchError
from lol_audio_unpack.manager.files import needs_update, write_data
from lol_audio_unpack.model.binding import (
    RESOURCE_SCHEMA_VERSION,
    BankBinding,
    BinBinding,
    BindingRole,
    BindingStatus,
)

pytestmark = pytest.mark.unit


def _bin_binding(path: str, status: BindingStatus) -> BinBinding:
    """构造 processor 测试使用的 BIN binding。"""
    return BinBinding(
        path=path,
        normalized_path="",
        wad="Game/DATA/FINAL/Shared.wad.client" if status is BindingStatus.RESOLVED else None,
        entry_hash=f"{len(path):016x}",
        status=status,
        role=BindingRole.ROOT if status is BindingStatus.RESOLVED else None,
    )


def test_champion_first_missing_bin_keeps_later_binding_and_writes_partial_v2(tmp_path: Path, monkeypatch) -> None:
    """首个 BIN 缺失时，后续成功项仍应生成 partial v2 artifact。"""
    first = "data/characters/Test/skins/skin0001.bin"
    second = "data/characters/Test/skins/skin0002.bin"
    batch = BinBatch(
        raws={second: b"second"},
        bindings=[_bin_binding(first, BindingStatus.MISSING), _bin_binding(second, BindingStatus.RESOLVED)],
        resource_v2=True,
    )

    fake_bin = SimpleNamespace(
        theme_music=None,
        data=[
            SimpleNamespace(
                music=None,
                bank_units=[
                    SimpleNamespace(
                        category="Characters/Test/Skins/Skin2/VO",
                        bank_path=["assets/sounds/wwise2016/vo/test_audio.bnk"],
                        events=[],
                    )
                ],
            )
        ],
    )
    bank_binding = BankBinding(
        category="Characters/Test/Skins/Skin2/VO",
        path="assets/sounds/wwise2016/vo/test_audio.bnk",
        normalized_path="",
        kind="BNK",
        wad="Game/DATA/FINAL/Shared.zh_CN.wad.client",
        entry_hash="0000000000000002",
        source_bin=second,
        role=BindingRole.LOCALIZED,
        status=BindingStatus.RESOLVED,
        sub_entity="2",
        group=0,
    )

    source = SimpleNamespace(
        _is_local_bin_mode_enabled=lambda: False,
        _uses_resource_v2=lambda: True,
        _resolve_bin_resources=lambda *_args, **_kwargs: batch,
        _resolve_bank_bindings=lambda _references: [bank_binding],
        _resource_index_diagnostics=lambda: ({"requests": 3}, []),
        _create_base_data=lambda entity_id, _entity_type, **extra: {
            "metadata": {"gameVersion": "16.16"},
            "championId": entity_id,
            **extra,
        },
    )
    processor = champion_module.ChampionBinProcessor.__new__(champion_module.ChampionBinProcessor)
    processor.ctx = SimpleNamespace(config=SimpleNamespace(dev_mode=False))
    processor.force_update = False
    processor.process_events = False
    processor.version = "16.16"
    processor.game_path = tmp_path
    processor.champion_banks_dir = tmp_path / "banks" / "champions"
    processor.champion_events_dir = tmp_path / "events" / "champions"
    processor.bin_source = source

    written: list[dict] = []
    monkeypatch.setattr(champion_module, "BIN", lambda raw: fake_bin if raw == b"second" else None)
    monkeypatch.setattr(champion_module, "needs_update", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(champion_module, "write_data", lambda data, *_args, **_kwargs: written.append(data))

    processor._process_champion_skins(
        {
            "alias": "Test",
            "skins": [
                {"id": "1", "isBase": True, "binPath": first},
                {"id": "2", "isBase": False, "binPath": second},
            ],
        },
        "90001",
    )

    assert len(written) == 1
    artifact = written[0]
    assert artifact["resourceSchemaVersion"] == RESOURCE_SCHEMA_VERSION
    assert [binding["status"] for binding in artifact["binBindings"]] == ["missing", "resolved"]
    assert artifact["diagnostics"]["completeness"] == "partial"
    assert artifact["skins"]["2"]["Characters/Test/Skins/Skin2/VO"] == [["assets/sounds/wwise2016/vo/test_audio.bnk"]]


def test_remote_local_bin_flag_short_circuits_wad_index(tmp_path: Path, monkeypatch) -> None:
    """remote `.use_local_bin` 必须在创建本地 WAD index 前直接读取准备好的 BIN。"""
    source = bin_source_module.BinSource.__new__(bin_source_module.BinSource)
    source.ctx = SimpleNamespace(config=SimpleNamespace(dev_mode=False), runtime_cache={})
    source.game_path = tmp_path
    source.local_bin_input_dir = tmp_path / "bin_input"
    source.use_local_bin_flag_file = tmp_path / ".use_local_bin"
    source.use_local_bin_flag_file.write_text("", encoding="utf-8")
    target = source.local_bin_input_dir / "data/characters/Test/skin.bin"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"remote-bin")

    monkeypatch.setattr(source, "_get_wad_index", lambda: pytest.fail("remote 不应创建本地 WAD index"))

    batch = source._resolve_bin_resources(
        ["data/characters/Test/skin.bin"],
        "英雄 1",
        local_required_dir=Path("data/characters/Test"),
    )

    assert batch.resource_v2 is False
    assert batch.bindings == []
    assert batch.raws == {"data/characters/Test/skin.bin": b"remote-bin"}


def test_remote_without_prepared_bin_does_not_fall_through_to_local_index(tmp_path: Path, monkeypatch) -> None:
    """remote 输入未准备完成时也不得意外接管为 local resolver。"""
    source = bin_source_module.BinSource.__new__(bin_source_module.BinSource)
    source.ctx = SimpleNamespace(
        config=SimpleNamespace(dev_mode=False, source_mode=SourceMode.REMOTE_SNAPSHOT),
        runtime_cache={},
    )
    source.game_path = tmp_path
    source.local_bin_input_dir = tmp_path / "bin_input"
    source.use_local_bin_flag_file = tmp_path / ".use_local_bin"
    monkeypatch.setattr(source, "_get_wad_index", lambda: pytest.fail("remote 不应创建本地 WAD index"))

    batch = source._resolve_bin_resources(["data/test.bin"], "英雄 1")

    assert batch.resource_v2 is False
    assert batch.raws == {}
    assert batch.bindings == []


def test_map_processor_keeps_common_binding_but_deduplicates_legacy_projection(tmp_path: Path, monkeypatch) -> None:
    """Common 去重只作用于旧投影，不得删除 v2 物理绑定。"""
    bin_path = "data/maps/shipping/map22/map22.bin"
    bank_path = "assets/sounds/wwise2016/sfx/map22_audio.bnk"
    common_path = "assets/sounds/wwise2016/sfx/common_audio.bnk"
    batch = BinBatch(
        raws={bin_path: b"map"},
        bindings=[_bin_binding(bin_path, BindingStatus.RESOLVED)],
        resource_v2=True,
    )
    fake_bin = SimpleNamespace(
        theme_music=None,
        data=[
            SimpleNamespace(
                music=None,
                bank_units=[
                    SimpleNamespace(category="Map22_SFX", bank_path=[bank_path], events=[]),
                    SimpleNamespace(category="Common_SFX", bank_path=[common_path], events=[]),
                ],
            )
        ],
    )
    bank_binding = BankBinding(
        category="Map22_SFX",
        path=bank_path,
        normalized_path="",
        kind="BNK",
        wad="Game/DATA/FINAL/Maps/Shipping/Map22.wad.client",
        entry_hash="0000000000000022",
        source_bin=bin_path,
        role=BindingRole.ROOT,
        status=BindingStatus.RESOLVED,
        sub_entity="22",
        group=0,
    )
    common_binding = BankBinding(
        category="Common_SFX",
        path=common_path,
        normalized_path="",
        kind="BNK",
        wad="Game/DATA/FINAL/Maps/Shipping/Map22.wad.client",
        entry_hash="0000000000000000",
        source_bin=bin_path,
        role=BindingRole.ROOT,
        status=BindingStatus.RESOLVED,
        sub_entity="22",
        group=1,
    )
    source = SimpleNamespace(
        _is_local_bin_mode_enabled=lambda: False,
        _uses_resource_v2=lambda: True,
        _load_map_bin_resource=lambda *_args: LoadedBin(fake_bin, batch),
        _resolve_bank_bindings=lambda _references: [bank_binding, common_binding],
        _resource_index_diagnostics=lambda: ({"requests": 2}, []),
        _create_base_data=lambda entity_id, _entity_type, **extra: {
            "metadata": {"gameVersion": "16.16"},
            "mapId": entity_id,
            **extra,
        },
    )
    processor = map_module.MapBinProcessor.__new__(map_module.MapBinProcessor)
    processor.ctx = SimpleNamespace(config=SimpleNamespace(dev_mode=False), runtime_cache={})
    processor.force_update = False
    processor.process_events = False
    processor.version = "16.16"
    processor.languages = ["zh_CN"]
    processor.map_banks_dir = tmp_path / "banks" / "maps"
    processor.map_events_dir = tmp_path / "events" / "maps"
    processor.bin_source = source

    written: list[dict] = []
    monkeypatch.setattr(map_module, "needs_update", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(map_module, "write_data", lambda data, *_args, **_kwargs: written.append(data))

    processor._process_single_map(
        "22",
        {"binPath": bin_path, "names": {"zh_CN": "云顶之弈"}},
        common_banks_set={(common_path,)},
    )

    assert len(written) == 1
    artifact = written[0]
    assert artifact["entity"] == {"type": "map", "id": "22"}
    assert [binding["path"] for binding in artifact["bankBindings"]] == [bank_path, common_path]
    assert all(binding["wad"].endswith("Map22.wad.client") for binding in artifact["bankBindings"])
    assert artifact["diagnostics"]["completeness"] == "complete"
    assert artifact["banks"] == {"Map22_SFX": [[bank_path]]}


def test_needs_update_distinguishes_local_resource_schema_from_legacy_freshness(tmp_path: Path) -> None:
    """相同 gameVersion 的旧 local banks 仍需重建，remote 旧检查保持可复用。"""
    base = tmp_path / "banks" / "1"
    base.parent.mkdir(parents=True)
    write_data({"metadata": {"gameVersion": "16.16"}, "skins": {}}, base, dev_mode=True)

    assert needs_update(base, "16.16", False, dev_mode=True) is False
    assert needs_update(base, "16.16", False, dev_mode=True, resource_schema=RESOURCE_SCHEMA_VERSION) is True

    write_data(
        {"metadata": {"gameVersion": "16.16"}, "resourceSchemaVersion": RESOURCE_SCHEMA_VERSION},
        base,
        dev_mode=True,
    )

    assert needs_update(base, "16.16", False, dev_mode=True, resource_schema=RESOURCE_SCHEMA_VERSION) is False


@pytest.mark.parametrize(
    ("source_mode", "raises"),
    [(SourceMode.LOCAL_PATH, True), (SourceMode.REMOTE_SNAPSHOT, False)],
)
def test_data_reader_requires_v2_only_for_local_artifacts(
    tmp_path: Path,
    monkeypatch,
    source_mode: SourceMode,
    raises: bool,
) -> None:
    """显式 require 在 local 拒绝 v1，在 remote 继续返回旧投影。"""
    reader = DataReader.__new__(DataReader)
    reader.ctx = SimpleNamespace(config=SimpleNamespace(dev_mode=False, source_mode=source_mode))
    reader.champion_banks_dir = tmp_path / "banks"
    reader._champion_banks_cache = {}
    monkeypatch.setattr(
        data_reader_module,
        "read_data",
        lambda *_args, **_kwargs: {"metadata": {"gameVersion": "16.16"}, "skins": {}},
    )

    assert reader.get_champion_banks(1) is not None
    if raises:
        with pytest.raises(ResourceSchemaMismatchError, match="重新运行 update"):
            reader.get_champion_banks(1, require_bindings=True)
    else:
        assert reader.get_champion_banks(1, require_bindings=True) is not None
        assert reader.get_champion_resource_bindings(1) is None
