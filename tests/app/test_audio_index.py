"""应用层 WEM 输出索引测试。"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from lol_audio_unpack.app.artifacts import enumerate_audio_refs
from lol_audio_unpack.app.path_layout import format_entity_folder_name, format_sub_entity_folder_name
from lol_audio_unpack.model import AudioEntityData


def _build_ctx(
    tmp_path: Path,
    *,
    group_by_type: bool,
    include_types: tuple[str, ...] = ("VO", "SFX"),
) -> SimpleNamespace:
    """创建 AudioRef 枚举所需的最小上下文。"""
    return SimpleNamespace(
        config=SimpleNamespace(group_by_type=group_by_type, include_types=include_types),
        paths=SimpleNamespace(audio_path=tmp_path / "audios"),
    )


def _build_entity() -> AudioEntityData:
    """创建具有两个可区分子实体的测试实体。"""
    return AudioEntityData(
        entity_id="1",
        entity_name="Annie",
        entity_alias="annie",
        entity_title="黑暗之女",
        entity_type="champion",
        sub_entities={
            "1000": {"name": "基础皮肤", "categories": {}},
            "1001": {"name": "哥特萝莉", "categories": {}},
        },
        wad_root="Game/root.wad.client",
    )


def test_enumerate_audio_refs_preserves_duplicate_ids_across_sub_entity_and_type(tmp_path: Path) -> None:
    """稳定引用应使用完整相对路径，不按 WEM ID 折叠。"""
    ctx = _build_ctx(tmp_path, group_by_type=False)
    entity = _build_entity()
    version = "16.16"
    entity_folder = format_entity_folder_name("1", "annie", "Annie", "黑暗之女")
    base = ctx.paths.audio_path / version / "champions" / entity_folder
    skin0 = format_sub_entity_folder_name("1000", "基础皮肤")
    skin1 = format_sub_entity_folder_name("1001", "哥特萝莉")
    (base / skin0 / "VO").mkdir(parents=True)
    (base / skin1 / "SFX").mkdir(parents=True)
    (base / "lobby").mkdir(parents=True)
    (base / skin0 / "VO" / "101.wem").write_bytes(b"vo")
    (base / skin1 / "SFX" / "101.wem").write_bytes(b"sfx")
    (base / "lobby" / "101.wem").write_bytes(b"lobby")

    refs = enumerate_audio_refs(ctx, entity, version)

    assert [ref.relative_path for ref in refs] == sorted(ref.relative_path for ref in refs)
    assert [ref.wem_id for ref in refs] == ["101", "101", "101"]
    assert {(ref.audio_type, ref.sub_entity) for ref in refs} == {
        ("LOBBY", None),
        ("SFX", "1001"),
        ("VO", "1000"),
    }
    assert all("/" in ref.key for ref in refs)
    assert all(entity_folder not in ref.key for ref in refs)


def test_enumerate_audio_refs_uses_grouped_layout_and_rejects_escaping_symlink(tmp_path: Path) -> None:
    """grouped 布局应保留类型段，且外部 symlink 不得进入引用集。"""
    ctx = _build_ctx(tmp_path, group_by_type=True, include_types=("VO",))
    entity = _build_entity()
    version = "16.16"
    entity_folder = format_entity_folder_name("1", "annie", "Annie", "黑暗之女")
    skin0 = format_sub_entity_folder_name("1000", "基础皮肤")
    target_dir = ctx.paths.audio_path / version / "VO" / "champions" / entity_folder / skin0
    target_dir.mkdir(parents=True)
    (target_dir / "201.wem").write_bytes(b"vo")
    excluded_type_dir = ctx.paths.audio_path / version / "SFX" / "champions" / entity_folder / skin0
    excluded_type_dir.mkdir(parents=True)
    (excluded_type_dir / "202.wem").write_bytes(b"sfx")
    outside = tmp_path / "outside.wem"
    outside.write_bytes(b"outside")
    link = target_dir / "escape.wem"
    try:
        os.symlink(outside, link)
    except OSError:
        pytest.skip("当前 Windows 测试环境不允许创建 symlink")

    refs = enumerate_audio_refs(ctx, entity, version)

    assert [(ref.relative_path, ref.audio_type, ref.sub_entity) for ref in refs] == [
        (f"SFX/{skin0}/202.wem", "SFX", "1000"),
        (f"VO/{skin0}/201.wem", "VO", "1000"),
    ]


def test_enumerate_audio_refs_rejects_symlink_that_escapes_only_the_entity_root(tmp_path: Path) -> None:
    """即使 symlink 仍在版本目录内，也不能跨到另一个实体输出根。"""
    ctx = _build_ctx(tmp_path, group_by_type=False)
    entity = _build_entity()
    version = "16.16"
    entity_folder = format_entity_folder_name("1", "annie", "Annie", "黑暗之女")
    entity_root = ctx.paths.audio_path / version / "champions" / entity_folder
    entity_root.mkdir(parents=True)
    other = ctx.paths.audio_path / version / "champions" / "2-other" / "301.wem"
    other.parent.mkdir(parents=True)
    other.write_bytes(b"other")
    try:
        os.symlink(other, entity_root / "301.wem")
    except OSError:
        pytest.skip("当前 Windows 测试环境不允许创建 symlink")

    assert enumerate_audio_refs(ctx, entity, version) == ()
