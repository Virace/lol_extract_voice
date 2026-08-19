"""selected-WAD resource-pack 发现的边界与 artifact 合同测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import lol_audio_unpack.manager.resource_pack_discovery as discovery_module
from lol_audio_unpack.app.resource_pack import (
    ResourcePackSelectionError,
    ResourcePackStaleSelectionError,
    ResourcePackWadRef,
    build_resource_pack_key,
    build_resource_pack_key_for_wad,
    parse_resource_pack_key,
    partition_special_targets,
    resource_pack_path_component,
)
from lol_audio_unpack.manager.data_reader import DataReader
from lol_audio_unpack.manager.files import read_data, write_data
from lol_audio_unpack.manager.resource_pack_discovery import (
    MAX_ENTRY_UNCOMPRESSED_BYTES,
    ResourcePackDiscovery,
)
from lol_audio_unpack.model.binding import BindingRole, BindingStatus, normalize_logical_path
from tests.runtime.test_wad_index import _FakeWad, _Section

pytestmark = pytest.mark.unit


class _Resolver:
    """最小 P1 resolver 边界，保留被请求路径而不读取 WAD payload。"""

    def __init__(self, *, missing_paths: set[str] | None = None):
        self.calls: list[tuple[str, ...]] = []
        self.missing_paths = missing_paths or set()

    def resolve_many(self, requests):
        """为 bank path 返回受控的 P1 风格 resolution。"""
        self.calls.append(tuple(request.path for request in requests))
        results = []
        for index, request in enumerate(requests, start=1):
            status = BindingStatus.MISSING if request.path in self.missing_paths else BindingStatus.RESOLVED
            results.append(
                SimpleNamespace(
                    normalized_path=normalize_logical_path(request.path),
                    wad=None if status is BindingStatus.MISSING else "Game/DATA/FINAL/Shared.wad.client",
                    entry_hash=f"{index:016x}",
                    role=None if status is BindingStatus.MISSING else BindingRole.ROOT,
                    status=status,
                    candidates=(),
                    diagnostic="not found" if status is BindingStatus.MISSING else None,
                )
            )
        return results


def _build_ctx(tmp_path: Path):
    """创建只包含 game FINAL 与 manifest artifact 根的本地上下文。"""
    game_root = tmp_path / "game"
    (game_root / "Game" / "DATA" / "FINAL").mkdir(parents=True)
    return SimpleNamespace(
        config=SimpleNamespace(
            game_path=game_root,
            game_region="zh_CN",
            dev_mode=True,
        ),
        paths=SimpleNamespace(manifest_path=tmp_path / "output" / "manifest"),
    )


def _selected_wad(ctx, name: str = "TFTCommon.wad.client") -> tuple[ResourcePackWadRef, Path]:
    """在 FINAL 下创建 selected-WAD 并返回其 typed snapshot。"""
    path = Path(ctx.config.game_path) / "Game" / "DATA" / "FINAL" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"selected")
    return ResourcePackWadRef.from_path(Path(ctx.config.game_path), path), path


def _section(
    path_hash: int,
    *,
    offset: int,
    storage_type: int = 0,
    size: int = 16,
    compressed_size: int = 8,
) -> _Section:
    """复用 P1 fake section，并补充 P5 candidate predicate 所需 storage type。"""
    section = _Section(path_hash=path_hash, offset=offset, size=size, compressed_size=compressed_size)
    section.type = storage_type
    return section


def _bin(category: str, paths: list[str], events: list[str] | None = None):
    """构造仅含 BANK_UNITS 的 BIN 解析结果，不复制上游 parser。"""
    return SimpleNamespace(
        data=[
            SimpleNamespace(
                bank_units=[
                    SimpleNamespace(
                        category=category,
                        bank_path=paths,
                        events=[SimpleNamespace(string=value) for value in events or []],
                    )
                ]
            )
        ]
    )


def test_zero_selection_touches_no_wad_and_selected_only_reads_payloads(tmp_path: Path) -> None:
    """空选择不构造 WAD；有选择时也只读取 selected-WAD 的 candidate payload。"""
    ctx = _build_ctx(tmp_path)
    ref, selected_path = _selected_wad(ctx)
    selected_wad = _FakeWad(
        [_section(1, offset=1), _section(2, offset=2), _section(3, offset=3, storage_type=4)],
        {1: b"PROPgood", 2: b"not-a-prop"},
    )
    constructed: list[Path] = []

    def wad_factory(path: Path) -> _FakeWad:
        constructed.append(path)
        assert path == selected_path
        return selected_wad

    resolver = _Resolver()
    discovery = ResourcePackDiscovery(
        ctx,
        wad_factory=wad_factory,
        bin_factory=lambda payload: (
            _bin("MODE_TFT_NPC_ElderDragon_SFX", ["assets/dragon.bnk"])
            if payload == b"PROPgood"
            else pytest.fail("非 PROP payload 不得交给 BIN parser")
        ),
        bank_resolver=resolver,
    )

    assert discovery.discover((), version="16.16").cost["payloadReads"] == 0
    assert constructed == []

    result = discovery.discover((ref,), version="16.16")

    assert constructed == [selected_path]
    assert selected_wad.extract_calls == [1, 2]
    assert result.status == "complete"
    assert result.packs[0].wad == ref.identity
    assert resolver.calls == [("assets/dragon.bnk",)]


def test_map_22_owned_bin_is_skipped_without_blocking_independent_candidate(tmp_path: Path) -> None:
    """Map 22 v2 ownership 只排除其声明 entry，不依赖 WAD 文件名前缀或阻断同包其它 BIN。"""
    map_id = 22
    ctx = _build_ctx(tmp_path)
    ref, _path = _selected_wad(ctx, "OpaqueContainer.wad.client")
    wad = _FakeWad(
        [_section(1, offset=1), _section(2, offset=2)],
        {1: b"PROPmap22", 2: b"PROPpack"},
    )
    reader = SimpleNamespace(
        get_map=lambda requested_id: {} if requested_id == map_id else pytest.fail("只应查询 Map 22"),
        get_map_resource_bindings=lambda _map_id: SimpleNamespace(
            bin_bindings=(SimpleNamespace(wad=ref.identity, entry_hash="0000000000000001"),)
        ),
    )

    result = ResourcePackDiscovery(
        ctx,
        reader=reader,
        wad_factory=lambda _path: wad,
        bin_factory=lambda payload: (
            _bin("MODE_TFT_INDEPENDENT_SFX", ["assets/independent.bnk"])
            if payload == b"PROPpack"
            else pytest.fail("Map 22 owned candidate 不得读取或解析")
        ),
        bank_resolver=_Resolver(),
    ).discover((ref,), version="16.16")

    assert result.status == "complete"
    assert len(result.packs) == 1
    assert wad.extract_calls == [2]
    assert result.scans[0].map_owned_entries_skipped == 1
    assert result.cost["mapOwnedEntriesSkipped"] == 1


def test_selection_rejects_escape_and_stale_stat_snapshot(tmp_path: Path) -> None:
    """选择与执行阶段都拒绝 FINAL 越界或已变化的 WAD。"""
    ctx = _build_ctx(tmp_path)
    outside = tmp_path / "outside.wad.client"
    outside.write_bytes(b"outside")

    with pytest.raises(ResourcePackSelectionError, match="FINAL"):
        ResourcePackWadRef.from_path(Path(ctx.config.game_path), outside)

    ref, selected = _selected_wad(ctx)
    selected.write_bytes(b"changed-size")

    with pytest.raises(ResourcePackStaleSelectionError, match="已变化"):
        ref.resolve(Path(ctx.config.game_path))

    missing_root = tmp_path / "missing-game"
    with pytest.raises(ResourcePackSelectionError, match="游戏根目录"):
        ResourcePackWadRef.from_path(missing_root, Path("Legacy.wad.client"))


def test_key_is_canonical_reversible_and_windows_safe() -> None:
    """stable key 使用 NFKC/casefold 编码，完整 key 的 artifact 名不含 Windows 禁止字符。"""
    key = build_resource_pack_key("ＴＦＴＣｏｍｍｏｎ.wad.client", "MODE/ＴＦＴ")

    assert key == "resource_pack:tftcommon:mode%2Ftft"
    assert parse_resource_pack_key(key).value == key
    component = resource_pack_path_component(key)
    assert ":" not in component
    assert "/" not in component
    assert "%3A" in component

    with pytest.raises(ValueError, match="canonical"):
        parse_resource_pack_key("resource_pack:TFTCommon:mode%2Ftft")

    partition = partition_special_targets(("champion:66600", key, "champion:66600", key))
    assert partition.champion_targets == ("champion:66600",)
    assert partition.resource_pack_targets == (key,)


def test_discovery_enforces_budget_before_payload_read(tmp_path: Path) -> None:
    """超出单 entry 未压缩预算时不得读取任何 payload 或扩展扫描范围。"""
    ctx = _build_ctx(tmp_path)
    ref, _path = _selected_wad(ctx)
    wad = _FakeWad(
        [_section(1, offset=1, size=MAX_ENTRY_UNCOMPRESSED_BYTES + 1, compressed_size=8)],
        {1: b"too-large"},
    )
    discovery = ResourcePackDiscovery(
        ctx,
        wad_factory=lambda _path: wad,
        bin_factory=lambda _payload: pytest.fail("超预算时不得解析 BIN"),
        bank_resolver=_Resolver(),
    )

    result = discovery.discover((ref,), version="16.16")

    assert result.status == "failed"
    assert result.scans[0].payload_reads == 0
    assert wad.extract_calls == []


def test_discovery_enforces_selected_wad_compressed_budget_before_payload_read(tmp_path: Path) -> None:
    """多个安全 candidate 的压缩总量超预算时也不得开始解压。"""
    ctx = _build_ctx(tmp_path)
    ref, _path = _selected_wad(ctx)
    wad = _FakeWad(
        [_section(1, offset=1, compressed_size=8), _section(2, offset=2, compressed_size=8)],
        {1: b"PROPone", 2: b"PROPtwo"},
    )
    discovery = ResourcePackDiscovery(
        ctx,
        wad_factory=lambda _path: wad,
        bin_factory=lambda _payload: pytest.fail("超预算时不得解析 BIN"),
        bank_resolver=_Resolver(),
        max_selected_compressed_bytes=15,
    )

    result = discovery.discover((ref,), version="16.16")

    assert result.status == "failed"
    assert "压缩字节超出预算" in (result.scans[0].reason or "")
    assert result.scans[0].payload_reads == 0
    assert wad.extract_calls == []


def test_duplicate_declarations_merge_source_hashes_and_partial_parse_keeps_pack(tmp_path: Path) -> None:
    """同 WAD/category 的逻辑 path 去重并保留来源；坏 candidate 不阻断其它成功 pack。"""
    ctx = _build_ctx(tmp_path)
    ref, _path = _selected_wad(ctx)
    wad = _FakeWad(
        [_section(1, offset=1), _section(2, offset=2), _section(3, offset=3)],
        {1: b"PROPfirst", 2: b"PROPsecond", 3: b"PROPbad"},
    )
    category = "MODE_TFT_NPC_ElderDragon_SFX"

    def bin_factory(payload: bytes):
        if payload == b"PROPfirst":
            return _bin(category, ["assets/dragon.bnk", "assets/common.wpk"], ["Play_A", "Play_A"])
        if payload == b"PROPsecond":
            return _bin(category, ["assets/DRAGON.bnk", "assets/second.bnk"], ["Play_B"])
        raise ValueError("not PROP")

    result = ResourcePackDiscovery(
        ctx,
        wad_factory=lambda _path: wad,
        bin_factory=bin_factory,
        bank_resolver=_Resolver(),
    ).discover((ref,), version="16.16")

    key = build_resource_pack_key_for_wad(ref, category)
    banks_base = (
        Path(ctx.paths.manifest_path) / "16.16" / "banks" / "resource_packs" / resource_pack_path_component(key)
    )
    events_base = (
        Path(ctx.paths.manifest_path) / "16.16" / "events" / "resource_packs" / resource_pack_path_component(key)
    )
    banks = read_data(banks_base, dev_mode=True)
    events = read_data(events_base, dev_mode=True)

    assert result.status == "partial"
    assert result.packs[0].status == "partial"
    assert result.packs[0].completeness == "complete"
    assert "BIN 内容解析失败" in (result.scans[0].reason or "")
    assert [binding["normalizedPath"] for binding in banks["bankBindings"]] == [
        "assets/common.wpk",
        "assets/dragon.bnk",
        "assets/second.bnk",
    ]
    source_hashes = {item["normalizedPath"]: item["entryHashes"] for item in banks["resourcePack"]["bankSources"]}
    assert source_hashes["assets/dragon.bnk"] == ["0000000000000001", "0000000000000002"]
    expected_candidate_count = len(wad.files)
    assert banks["resourcePack"]["discovery"]["status"] == "partial"
    assert banks["resourcePack"]["discovery"]["candidateEntries"] == expected_candidate_count
    assert banks["resourcePack"]["discovery"]["payloadReads"] == expected_candidate_count
    assert events["events"] == {category: ["Play_A", "Play_B"]}

    reader = DataReader.__new__(DataReader)
    reader.ctx = ctx
    reader.resource_pack_banks_dir = banks_base.parent
    reader.resource_pack_events_dir = events_base.parent
    reader._resource_pack_banks_cache = {}
    reader._resource_pack_events_cache = {}

    bindings = reader.get_resource_pack_resource_bindings(key)
    assert bindings is not None
    assert bindings.entity_type == "resource_pack"
    assert bindings.entity_id == key
    assert reader.get_resource_pack_events(key) == events


def test_conflicting_existing_artifact_is_never_overwritten_and_reader_reads_v2(tmp_path: Path) -> None:
    """同 key 的不同 source identity 拒绝覆盖；DataReader 可按 stable key 读取新 artifact。"""
    ctx = _build_ctx(tmp_path)
    ref, _path = _selected_wad(ctx)
    category = "MODE_TFT_NPC_RiftHerald_SFX"
    key = build_resource_pack_key_for_wad(ref, category)
    base = Path(ctx.paths.manifest_path) / "16.16" / "banks" / "resource_packs" / resource_pack_path_component(key)
    base.parent.mkdir(parents=True)
    existing = {
        "resourcePack": {
            "wad": "Game/DATA/FINAL/Other.wad.client",
            "sourceFingerprint": "different",
        }
    }
    write_data(existing, base, dev_mode=True)

    wad = _FakeWad([_section(1, offset=1)], {1: b"PROPgood"})
    result = ResourcePackDiscovery(
        ctx,
        wad_factory=lambda _path: wad,
        bin_factory=lambda _payload: _bin(category, ["assets/rift.bnk"]),
        bank_resolver=_Resolver(),
    ).discover((ref,), version="16.16")

    assert result.status == "failed"
    assert "conflict" in (result.scans[0].reason or "")
    assert result.packs[0].status == "conflict"
    assert read_data(base, dev_mode=True) == existing

    reader = DataReader.__new__(DataReader)
    reader.ctx = ctx
    reader.resource_pack_banks_dir = base.parent
    reader.resource_pack_events_dir = Path(ctx.paths.manifest_path) / "16.16" / "events" / "resource_packs"
    reader._resource_pack_banks_cache = {}
    reader._resource_pack_events_cache = {}

    assert reader.get_resource_pack_banks(key) == existing
    with pytest.raises(ValueError, match="resource schema v2"):
        reader.get_resource_pack_resource_bindings(key)


def test_artifact_write_failure_is_reported_and_does_not_publish_banks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """共享 writer 静默失败后必须回读判错，且 banks 提交点不得对 catalog 可见。"""
    ctx = _build_ctx(tmp_path)
    ref, _path = _selected_wad(ctx)
    category = "MODE_TFT_WRITE_FAILURE_SFX"
    key = build_resource_pack_key_for_wad(ref, category)
    component = resource_pack_path_component(key)
    banks_base = Path(ctx.paths.manifest_path) / "16.16" / "banks" / "resource_packs" / component
    events_base = Path(ctx.paths.manifest_path) / "16.16" / "events" / "resource_packs" / component
    wad = _FakeWad([_section(1, offset=1)], {1: b"PROPgood"})

    def swallow_events_write(data: dict, base: Path, *, dev_mode: bool) -> None:
        """模拟共享 writer 已记录异常但没有向调用者抛出。"""
        if "events" in base.parts:
            return
        write_data(data, base, dev_mode=dev_mode)

    monkeypatch.setattr(discovery_module, "write_data", swallow_events_write)
    result = ResourcePackDiscovery(
        ctx,
        wad_factory=lambda _path: wad,
        bin_factory=lambda _payload: _bin(category, ["assets/failure.bnk"]),
        bank_resolver=_Resolver(),
    ).discover((ref,), version="16.16")

    assert result.status == "failed"
    assert result.packs[0].status == "failed"
    assert not read_data(events_base, dev_mode=True)
    assert not read_data(banks_base, dev_mode=True)


def test_banks_write_failure_restores_existing_banks_and_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """已有 artifact 更新到一半时必须恢复两份旧文件，不能混用新旧 payload。"""
    ctx = _build_ctx(tmp_path)
    ref, _path = _selected_wad(ctx)
    category = "MODE_TFT_TRANSACTION_SFX"
    key = build_resource_pack_key_for_wad(ref, category)
    component = resource_pack_path_component(key)
    banks_base = Path(ctx.paths.manifest_path) / "16.16" / "banks" / "resource_packs" / component
    events_base = Path(ctx.paths.manifest_path) / "16.16" / "events" / "resource_packs" / component
    wad = _FakeWad([_section(1, offset=1)], {1: b"PROPgood"})

    first = ResourcePackDiscovery(
        ctx,
        wad_factory=lambda _path: wad,
        bin_factory=lambda _payload: _bin(category, ["assets/transaction.bnk"], ["Play_Old"]),
        bank_resolver=_Resolver(),
    ).discover((ref,), version="16.16")
    assert first.status == "complete"
    old_banks = read_data(banks_base, dev_mode=True)
    old_events = read_data(events_base, dev_mode=True)

    def swallow_banks_write(data: dict, base: Path, *, dev_mode: bool) -> None:
        """允许新 events 落盘，但模拟 banks writer 静默失败。"""
        if "banks" in base.parts:
            return
        write_data(data, base, dev_mode=dev_mode)

    monkeypatch.setattr(discovery_module, "write_data", swallow_banks_write)
    second = ResourcePackDiscovery(
        ctx,
        wad_factory=lambda _path: wad,
        bin_factory=lambda _payload: _bin(category, ["assets/transaction.bnk"], ["Play_New"]),
        bank_resolver=_Resolver(),
    ).discover((ref,), version="16.16")

    assert second.status == "failed"
    assert second.packs[0].status == "failed"
    assert read_data(banks_base, dev_mode=True) == old_banks
    assert read_data(events_base, dev_mode=True) == old_events


def test_normalized_namespace_collision_is_reported_without_writing_artifact(tmp_path: Path) -> None:
    """同一 WAD 内不同原始 namespace 归一化到同 key 时不得顺序覆盖。"""
    ctx = _build_ctx(tmp_path)
    ref, _path = _selected_wad(ctx)
    wad = _FakeWad(
        [_section(1, offset=1), _section(2, offset=2)],
        {1: b"PROPupper", 2: b"PROPlower"},
    )

    def bin_factory(payload: bytes):
        if payload == b"PROPupper":
            return _bin("MODE_TFT_NPC_ElderDragon_SFX", ["assets/upper.bnk"])
        return _bin("mode_tft_npc_elderdragon_sfx", ["assets/lower.bnk"])

    result = ResourcePackDiscovery(
        ctx,
        wad_factory=lambda _path: wad,
        bin_factory=bin_factory,
        bank_resolver=_Resolver(),
    ).discover((ref,), version="16.16")

    key = build_resource_pack_key_for_wad(ref, "MODE_TFT_NPC_ElderDragon_SFX")
    base = Path(ctx.paths.manifest_path) / "16.16" / "banks" / "resource_packs" / resource_pack_path_component(key)
    assert result.status == "failed"
    assert result.packs[0].status == "conflict"
    assert not read_data(base, dev_mode=True)


def test_reader_lists_each_artifact_base_once_and_skips_corrupt_rows(tmp_path: Path) -> None:
    """枚举 catalog 时沿用 artifact 格式优先级，坏行不得阻断其它资源包。"""
    ctx = _build_ctx(tmp_path)
    key = build_resource_pack_key("Ruby_Urgot.wad.client", "MODE_DOOM_BOTS")
    banks_dir = Path(ctx.paths.manifest_path) / "16.16" / "banks" / "resource_packs"
    base = banks_dir / resource_pack_path_component(key)
    banks_dir.mkdir(parents=True)
    payload = {"resourcePack": {"key": key}}
    write_data(payload, base, dev_mode=True)
    write_data(payload, base, dev_mode=False)
    write_data(payload, banks_dir / "wrong-name", dev_mode=True)
    corrupt = banks_dir / "corrupt.msgpack"
    corrupt.write_bytes(b"not-msgpack")

    reader = DataReader.__new__(DataReader)
    reader.ctx = ctx
    reader.resource_pack_banks_dir = banks_dir
    reader._resource_pack_banks_cache = {}

    artifacts = reader.list_resource_pack_banks()

    assert [artifact["resourcePack"]["key"] for artifact in artifacts] == [key]
