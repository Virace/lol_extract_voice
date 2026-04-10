"""应用层共享的解包与映射产物定位辅助。"""

from __future__ import annotations

from pathlib import Path

from lol_audio_unpack.app.path_layout import format_entity_folder_name, get_output_dir_name
from lol_audio_unpack.manager.files import find_data_file
from lol_audio_unpack.model import AudioEntityData

from .types import AppContext


def resolve_audio_paths(
    ctx: AppContext,
    entity_data: AudioEntityData,
    version: str,
) -> tuple[Path, ...]:
    """解析实体解包后的实际输出目录。

    Args:
        ctx: 当前应用上下文。
        entity_data: 实体数据对象。
        version: 当前数据版本号。

    Returns:
        实际存在的音频输出目录列表。
    """
    audio_base = Path(ctx.paths.audio_path)
    entity_dir = get_output_dir_name(entity_data.entity_type)
    entity_folder = format_entity_folder_name(
        entity_data.entity_id,
        entity_data.entity_alias,
        entity_data.entity_name,
        entity_data.entity_title,
    )
    audio_root = audio_base / version

    if ctx.config.group_by_type:
        grouped_paths = tuple(
            candidate
            for audio_type in ctx.config.include_types
            if (candidate := audio_root / audio_type / entity_dir / entity_folder).exists()
        )
        lobby_dir = audio_root / entity_dir / entity_folder / "lobby"
        if lobby_dir.exists():
            return (*grouped_paths, lobby_dir)
        return grouped_paths

    candidate = audio_root / entity_dir / entity_folder
    if candidate.exists():
        return (candidate,)
    return ()


def resolve_mapping_path(
    ctx: AppContext,
    *,
    entity_dir: str,
    entity_id: int | str,
    version: str,
    integrate_data: bool | None = None,
) -> Path | None:
    """解析实体映射文件的实际路径。

    Args:
        ctx: 当前应用上下文。
        entity_dir: 输出目录名，例如 ``champions`` 或 ``maps``。
        entity_id: 实体 ID。
        version: 当前数据版本号。
        integrate_data: 指定是否只查整合版或只查普通版。
            为 ``None`` 时先尝试整合版，再回退普通版。

    Returns:
        命中的映射文件路径；不存在时返回 ``None``。
    """
    hash_root = Path(ctx.paths.hash_path) / version
    base_paths = _build_mapping_bases(
        hash_root=hash_root,
        entity_dir=entity_dir,
        entity_id=entity_id,
        integrate_data=integrate_data,
    )
    dev_mode = getattr(ctx.config, "dev_mode", False)

    if integrate_data is None:
        for base_path in base_paths:
            if (resolved := find_data_file(base_path, dev_mode=dev_mode)) is not None:
                return resolved
        return None

    suffix = ".yml" if dev_mode else ".msgpack"
    for base_path in base_paths:
        candidate = base_path.with_suffix(suffix)
        if candidate.exists():
            return candidate
    return None


def _build_mapping_bases(
    *,
    hash_root: Path,
    entity_dir: str,
    entity_id: int | str,
    integrate_data: bool | None,
) -> tuple[Path, ...]:
    """构建映射文件的基础路径候选。"""
    entity_id_text = str(entity_id)
    integrated_base = hash_root / "integrated" / entity_dir / entity_id_text
    raw_base = hash_root / entity_dir / entity_id_text

    if integrate_data is True:
        return (integrated_base,)
    if integrate_data is False:
        return (raw_base,)
    return (integrated_base, raw_base)


__all__ = [
    "resolve_audio_paths",
    "resolve_mapping_path",
]
