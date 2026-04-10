"""`app.artifacts` 产物路径定位测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from lol_audio_unpack.app.artifacts import resolve_audio_paths, resolve_mapping_path
from lol_audio_unpack.app.path_layout import format_entity_folder_name
from lol_audio_unpack.model import AudioEntityData


def _build_ctx(
    tmp_path: Path,
    *,
    group_by_type: bool,
    include_types: tuple[str, ...] = ("VO", "SFX"),
    dev_mode: bool = False,
):
    output_root = tmp_path / "output"
    return SimpleNamespace(
        config=SimpleNamespace(
            group_by_type=group_by_type,
            include_types=include_types,
            dev_mode=dev_mode,
        ),
        paths=SimpleNamespace(
            audio_path=output_root / "audios",
            hash_path=output_root / "hashes",
        ),
    )


def _build_entity() -> AudioEntityData:
    return AudioEntityData(
        entity_id="1",
        entity_name="Annie",
        entity_alias="annie",
        entity_title="黑暗之女",
        entity_type="champion",
        sub_entities={"1000": {"name": "基础皮肤", "categories": {}}},
        wad_root="Game/DATA/FINAL/Champions/Annie.wad.client",
        wad_language="Game/DATA/FINAL/Champions/Annie.zh_CN.wad.client",
    )


def _entity_folder(entity: AudioEntityData) -> str:
    return format_entity_folder_name(
        entity.entity_id,
        entity.entity_alias,
        entity.entity_name,
        entity.entity_title,
    )


def test_resolve_audio_paths_returns_existing_grouped_type_dirs(tmp_path: Path) -> None:
    ctx = _build_ctx(tmp_path, group_by_type=True, include_types=("VO", "SFX", "MUSIC"))
    entity = _build_entity()
    version = "15.7"
    entity_folder = _entity_folder(entity)

    vo_dir = ctx.paths.audio_path / version / "VO" / "champions" / entity_folder
    sfx_dir = ctx.paths.audio_path / version / "SFX" / "champions" / entity_folder
    vo_dir.mkdir(parents=True)
    sfx_dir.mkdir(parents=True)

    assert resolve_audio_paths(ctx, entity, version) == (vo_dir, sfx_dir)


def test_resolve_audio_paths_grouped_type_includes_lobby_dir_when_present(tmp_path: Path) -> None:
    ctx = _build_ctx(tmp_path, group_by_type=True, include_types=("VO", "SFX", "MUSIC"))
    entity = _build_entity()
    version = "15.7"
    entity_folder = _entity_folder(entity)

    vo_dir = ctx.paths.audio_path / version / "VO" / "champions" / entity_folder
    lobby_dir = ctx.paths.audio_path / version / "champions" / entity_folder / "lobby"
    vo_dir.mkdir(parents=True)
    lobby_dir.mkdir(parents=True)

    assert resolve_audio_paths(ctx, entity, version) == (vo_dir, lobby_dir)


def test_resolve_audio_paths_returns_flat_entity_dir_when_not_grouped(tmp_path: Path) -> None:
    ctx = _build_ctx(tmp_path, group_by_type=False)
    entity = _build_entity()
    version = "15.7"
    entity_folder = _entity_folder(entity)

    entity_dir = ctx.paths.audio_path / version / "champions" / entity_folder
    entity_dir.mkdir(parents=True)

    assert resolve_audio_paths(ctx, entity, version) == (entity_dir,)


def test_resolve_mapping_path_prefers_integrated_then_raw_with_fallback_suffixes(tmp_path: Path) -> None:
    ctx = _build_ctx(tmp_path, group_by_type=False, dev_mode=False)
    version = "15.7"
    raw_path = ctx.paths.hash_path / version / "champions" / "1.yml"
    integrated_path = ctx.paths.hash_path / version / "integrated" / "champions" / "1.msgpack"

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("raw", encoding="utf-8")

    assert (
        resolve_mapping_path(
            ctx,
            entity_dir="champions",
            entity_id="1",
            version=version,
        )
        == raw_path
    )

    integrated_path.parent.mkdir(parents=True, exist_ok=True)
    integrated_path.write_bytes(b"integrated")

    assert (
        resolve_mapping_path(
            ctx,
            entity_dir="champions",
            entity_id="1",
            version=version,
        )
        == integrated_path
    )


def test_resolve_mapping_path_exact_mode_does_not_fall_back_to_other_suffixes(tmp_path: Path) -> None:
    ctx = _build_ctx(tmp_path, group_by_type=False, dev_mode=False)
    version = "15.7"
    raw_yml = ctx.paths.hash_path / version / "champions" / "1.yml"
    raw_yml.parent.mkdir(parents=True, exist_ok=True)
    raw_yml.write_text("raw", encoding="utf-8")

    assert (
        resolve_mapping_path(
            ctx,
            entity_dir="champions",
            entity_id="1",
            version=version,
            integrate_data=False,
        )
        is None
    )
