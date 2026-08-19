"""应用层共享的解包与映射产物定位辅助。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lol_audio_unpack.app.path_layout import (
    AUDIO_TYPE_MUSIC,
    AUDIO_TYPE_SFX,
    AUDIO_TYPE_VO,
    DIR_RESOURCE_PACKS,
    ENTITY_NAME_SEPARATOR,
    format_entity_folder_name,
    get_entity_path_component,
    get_output_dir_name,
)
from lol_audio_unpack.manager.files import find_data_file
from lol_audio_unpack.model import AudioEntityData

from .types import AppContext

_MIN_AUDIO_REF_PARTS = 2
_INDEXED_AUDIO_TYPES = (AUDIO_TYPE_VO, AUDIO_TYPE_SFX, AUDIO_TYPE_MUSIC)


@dataclass(frozen=True)
class AudioRef:
    """一个已落盘 WEM 的稳定应用层引用。

    Args:
        relative_path: 相对于逻辑实体输出根的 POSIX 路径，也是持久化键。
        path: 已通过实体根目录 containment 校验的运行时绝对路径。
        wem_id: 原始 WEM ID（文件 stem）。
        audio_type: 可由输出布局可靠推导的音频类型。
        sub_entity: 可由输出布局可靠推导的逻辑子实体 ID。
    """

    relative_path: str
    path: Path
    wem_id: str
    audio_type: str | None
    sub_entity: str | None

    @property
    def key(self) -> str:
        """返回用于 artifact 的稳定相对路径键。"""
        return self.relative_path


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
        get_entity_path_component(entity_data.entity_type, entity_data.entity_id),
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


def enumerate_audio_refs(
    ctx: AppContext,
    entity_data: AudioEntityData,
    version: str,
) -> tuple[AudioRef, ...]:
    """枚举实体实际输出的 WEM，并拒绝经 symlink 逃逸的路径。

    Args:
        ctx: 当前应用上下文。
        entity_data: 实体数据对象。
        version: 当前数据版本号。

    Returns:
        按稳定 POSIX 相对路径排序的 WEM 引用。
    """
    version_root = (Path(ctx.paths.audio_path) / version).resolve()
    refs: list[AudioRef] = []
    seen: set[str] = set()

    for entity_root in _resolve_audio_ref_roots(ctx, entity_data, version):
        if not entity_root.is_dir():
            continue
        try:
            resolved_root = entity_root.resolve(strict=True)
            resolved_root.relative_to(version_root)
        except (OSError, ValueError):
            continue

        audio_type_prefix = _grouped_audio_type(entity_root, version_root) if ctx.config.group_by_type else None
        for candidate in entity_root.rglob("*.wem"):
            try:
                resolved_path = candidate.resolve(strict=True)
                resolved_path.relative_to(resolved_root)
            except (OSError, ValueError):
                # 产物目录可包含用户放入的 symlink；它们不应成为可播放或可持久化引用。
                continue

            physical_relative = candidate.relative_to(entity_root)
            if ctx.config.group_by_type:
                prefix = "lobby" if entity_root.name == "lobby" else audio_type_prefix
                if prefix is None:
                    continue
                logical_relative = Path(prefix) / physical_relative
            else:
                logical_relative = physical_relative
            relative = logical_relative.as_posix()

            if relative in seen:
                continue
            seen.add(relative)
            audio_type, sub_entity = _describe_audio_ref(entity_data, logical_relative, ctx=ctx)
            refs.append(
                AudioRef(
                    relative_path=relative,
                    path=resolved_path,
                    wem_id=candidate.stem,
                    audio_type=audio_type,
                    sub_entity=sub_entity,
                )
            )

    return tuple(sorted(refs, key=lambda item: item.relative_path))


def _resolve_audio_ref_roots(
    ctx: AppContext,
    entity_data: AudioEntityData,
    version: str,
) -> tuple[Path, ...]:
    """返回索引所需的全部已存在实体根，不受本次 include types 限制。"""
    if not ctx.config.group_by_type:
        return resolve_audio_paths(ctx, entity_data, version)

    audio_root = Path(ctx.paths.audio_path) / version
    entity_dir = get_output_dir_name(entity_data.entity_type)
    entity_folder = format_entity_folder_name(
        get_entity_path_component(entity_data.entity_type, entity_data.entity_id),
        entity_data.entity_alias,
        entity_data.entity_name,
        entity_data.entity_title,
    )
    roots = tuple(
        candidate
        for audio_type in _INDEXED_AUDIO_TYPES
        if (candidate := audio_root / audio_type / entity_dir / entity_folder).is_dir()
    )
    lobby_root = audio_root / entity_dir / entity_folder / "lobby"
    return (*roots, lobby_root) if lobby_root.is_dir() else roots


def _grouped_audio_type(entity_root: Path, version_root: Path) -> str | None:
    """从 grouped 实体根相对版本目录的位置读取音频类型。"""
    try:
        relative_parts = entity_root.resolve(strict=True).relative_to(version_root).parts
    except (OSError, ValueError):
        return None
    return relative_parts[0] if relative_parts and entity_root.name != "lobby" else None


def _describe_audio_ref(  # noqa: PLR0911
    entity_data: AudioEntityData,
    relative_path: Path,
    *,
    ctx: AppContext,
) -> tuple[str | None, str | None]:
    """按现有 grouped/non-grouped 输出布局推导 WEM 归属。"""
    parts = relative_path.parts

    if ctx.config.group_by_type:
        if len(parts) < _MIN_AUDIO_REF_PARTS:
            return None, None
        audio_type = "LOBBY" if parts[0] == "lobby" else parts[0]
        content_parts = parts[1:-1]
    else:
        if len(parts) < _MIN_AUDIO_REF_PARTS:
            return None, None
        content_parts = parts[:-1]
        if content_parts and content_parts[0] == "lobby":
            return "LOBBY", None
        if entity_data.entity_type == "champion" and len(content_parts) >= _MIN_AUDIO_REF_PARTS:
            audio_type = content_parts[1]
            content_parts = content_parts[:1]
        elif entity_data.entity_type == "map" and content_parts:
            audio_type = content_parts[0]
            content_parts = ()
        elif entity_data.entity_type == "resource_pack" and content_parts:
            audio_type = content_parts[0]
            content_parts = ()
        else:
            return None, None

    if entity_data.entity_type == "map":
        return audio_type, str(entity_data.entity_id)
    if entity_data.entity_type == "resource_pack":
        return audio_type, str(entity_data.entity_id)
    if not content_parts:
        return audio_type, None

    folder = content_parts[0]
    sub_id, separator, _name = folder.partition(ENTITY_NAME_SEPARATOR)
    return audio_type, sub_id if separator and sub_id.isdigit() else None


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
    entity_id_text = (
        get_entity_path_component("resource_pack", entity_id) if entity_dir == DIR_RESOURCE_PACKS else str(entity_id)
    )
    integrated_base = hash_root / "integrated" / entity_dir / entity_id_text
    raw_base = hash_root / entity_dir / entity_id_text

    if integrate_data is True:
        return (integrated_base,)
    if integrate_data is False:
        return (raw_base,)
    return (integrated_base, raw_base)


__all__ = [
    "AudioRef",
    "enumerate_audio_refs",
    "resolve_audio_paths",
    "resolve_mapping_path",
]
