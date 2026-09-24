"""应用层共享的解包与映射产物定位辅助。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from lol_audio_unpack.app.path_layout import (
    DIR_RESOURCE_PACKS,
    format_entity_folder_name,
    get_entity_path_component,
    get_output_dir_name,
)
from lol_audio_unpack.manager.files import find_data_file
from lol_audio_unpack.model import AudioEntityData
from lol_audio_unpack.model.skin_audio import SkinAudio
from lol_audio_unpack.runtime.library import MediaRef
from lol_audio_unpack.runtime.library.types import relative_path

from .outputs import load_outputs, output_summary, split_audio
from .types import AppContext


@dataclass(frozen=True)
class AudioRef:
    """一个已落盘 WEM 的稳定应用层引用。

    Args:
        relative_path: 相对于逻辑实体输出根的 POSIX 路径，也是持久化键。
        path: 由安全逻辑路径生成的绝对路径；实际使用时再核对文件与重解析点。
        wem_id: 原始 WEM ID（文件 stem）。
        audio_type: 可由输出布局可靠推导的音频类型。
        sub_entity: 可由输出布局可靠推导的逻辑子实体 ID。
    """

    relative_path: str
    path: Path
    wem_id: str
    audio_type: str | None
    sub_entity: str | None
    media: MediaRef | None = None
    root: Path | None = None
    region: str | None = None

    @property
    def key(self) -> str:
        """返回用于 artifact 的稳定相对路径键。"""
        return self.relative_path


@dataclass(frozen=True, slots=True)
class AudioIndexProgress:
    """全部音频路径索引的计数进度。

    Args:
        current: 已处理的 WEM 候选数。
        total: 本次发现的 WEM 候选总数；发现阶段尚未知时为 0。
    """

    current: int
    total: int


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
        输出清单已记录的实体目录列表，不检查磁盘上的瞬时状态。
    """
    return output_summary(
        ctx.config.output_path, version, ctx.game_region, entity_data.entity_type, str(entity_data.entity_id)
    )[1]


def enumerate_audio_refs(
    ctx: AppContext,
    entity_data: AudioEntityData,
    version: str,
    *,
    progress: Callable[[AudioIndexProgress], None] | None = None,
) -> tuple[AudioRef, ...]:
    """读取实体已登记的音频路径，文件与 symlink 检查留到实际使用时。

    Args:
        ctx: 当前应用上下文。
        entity_data: 实体数据对象。
        version: 当前数据版本号。
        progress: 可选的计数进度回调；最多按整数百分比更新一次。

    Returns:
        按稳定 POSIX 相对路径排序的 WEM 引用。
    """
    refs = []
    for path in load_outputs(
        ctx.config.output_path, version, ctx.game_region, entity_data.entity_type, str(entity_data.entity_id)
    ):
        root, logical, audio_type, sub_id = split_audio(path)
        refs.append(AudioRef(logical, path, path.stem, audio_type, sub_id, root=root, region=ctx.game_region))
    refs = tuple(refs)
    if progress is not None:
        progress(AudioIndexProgress(len(refs), len(refs)))
    return refs


def inspect_shared_copies(entity_data: AudioEntityData, refs: tuple[AudioRef, ...]) -> dict[str, list[str]]:
    """只读核对纯共享皮肤目录中的旧文件，不删除或隐藏任何产物。

    Args:
        entity_data: 当前英雄的完整资源声明。
        refs: 已通过路径边界检查的目录索引；应在后台任务中调用。

    Returns:
        有共享来源且逐字节相同的旧文件，以及内容不同、规范文件缺失或无法读取的待核对文件。
    """
    layout = SkinAudio(entity_data.resource_banks, entity_data.skin_parents)
    groups: dict[tuple[str, str], list] = {}
    for bank in entity_data.resource_banks:
        groups.setdefault((bank.sub_id, bank.audio_type), []).append(bank)
    owners = {
        key: {layout.owner(bank).sub_id for bank in banks}
        for key, banks in groups.items()
        if all(layout.is_shared((bank.sub_id, bank.binding.category)) for bank in banks)
    }
    by_key: dict[tuple[str | None, str | None, str], list[AudioRef]] = {}
    for ref in refs:
        by_key.setdefault((ref.sub_entity, ref.audio_type, ref.wem_id), []).append(ref)
    copies, unverified = [], []
    for ref in refs:
        source_ids = owners.get((ref.sub_entity, ref.audio_type))
        if not source_ids:
            continue
        candidates = [source for owner in source_ids for source in by_key.get((owner, ref.audio_type, ref.wem_id), ())]
        try:
            same = any(
                ref.media.object.digest == source.media.object.digest
                if ref.media is not None and source.media is not None
                else _matches_audio(ref.path, source.path)
                for source in candidates
            )
        except OSError:
            same = False
        (copies if same else unverified).append(ref.relative_path)
    return {"sharedCopyPaths": copies, "unverifiedSharedPaths": unverified}


def _matches_audio(first: Path, second: Path) -> bool:
    """逐块确认内容相等，避免仅凭 ID、文件尺寸或旧比较缓存识别副本。"""
    if first.stat().st_size != second.stat().st_size:
        return False
    with first.open("rb") as left, second.open("rb") as right:
        while chunk := left.read(64 * 1024):
            if chunk != right.read(len(chunk)):
                return False
        return not right.read(1)


def resolve_audio_refs(
    ctx: AppContext,
    entity_data: AudioEntityData,
    version: str,
    relative_paths: Iterable[str],
    *,
    roots: tuple[Path, ...] | None = None,
) -> tuple[AudioRef, ...]:
    """只解析调用方明确给出的实体内 WEM 相对路径。

    该入口仅解析事件 mapping 路径；重解析点和文件存在性留到播放、导出时检查。
    地图的两种布局均使用类型开头的逻辑路径，依据输出摘要选根，不探测每个媒体。

    Args:
        ctx: 当前应用上下文。
        entity_data: 实体数据对象。
        version: 当前数据版本号。
        relative_paths: 相对于逻辑实体输出根的 WEM 路径。
        roots: 已读取的输出根摘要，预览逐项解析时复用。

    Returns:
        通过逻辑路径校验的音频引用，不保证磁盘文件仍存在。
    """
    folder = format_entity_folder_name(
        get_entity_path_component(entity_data.entity_type, entity_data.entity_id),
        entity_data.entity_alias,
        entity_data.entity_name,
        entity_data.entity_title,
    )
    base = ctx.version_path("audio", version)
    entity = Path(get_output_dir_name(entity_data.entity_type)) / folder
    if roots is None and entity_data.entity_type != "champion":
        roots = resolve_audio_paths(ctx, entity_data, version)
    refs = []
    for value in sorted(set(relative_paths)):
        try:
            logical = relative_path(value)
        except ValueError:
            continue
        parts = Path(logical).parts
        if len(parts) < 2 or Path(logical).suffix.lower() not in {".wem", ".ogg"}:  # noqa: PLR2004
            continue
        grouped = parts[0] in {"VO", "SFX", "MUSIC"}
        if grouped and entity_data.entity_type != "champion":
            grouped = base / parts[0] / entity in (roots or ())
        root = base / parts[0] / entity if grouped else base / entity
        path = root.joinpath(*parts[1:]) if grouped else root / logical
        _, _, audio_type, sub_id = split_audio(path)
        refs.append(AudioRef(logical, path, path.stem, audio_type, sub_id, root=root, region=ctx.game_region))
    return tuple(refs)


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
            为 ``None`` 时选择最近生成的映射，时间相同时优先整合版。

    Returns:
        命中的映射文件路径；不存在时返回 ``None``。
    """
    return find_mapping(
        ctx.version_path("hash", version),
        entity_dir=entity_dir,
        entity_id=entity_id,
        integrate_data=integrate_data,
    )


def find_mapping(
    hash_root: Path,
    *,
    entity_dir: str,
    entity_id: int | str,
    integrate_data: bool | None = None,
) -> Path | None:
    """从固定版本和语言的哈希目录定位映射，不初始化游戏上下文。

    Args:
        hash_root: 已选版本和语言的 hashes 根目录。
        entity_dir: 实体目录名。
        entity_id: 实体 ID。
        integrate_data: 为空时选择最近生成的映射，同时间优先整合版。

    Returns:
        已有映射路径；未生成时返回 ``None``。
    """
    base_paths = _build_mapping_bases(
        hash_root=hash_root,
        entity_dir=entity_dir,
        entity_id=entity_id,
        integrate_data=integrate_data,
    )
    if integrate_data is None:
        candidates = [path for base in base_paths if (path := find_data_file(base)) is not None]
        return max(candidates, key=lambda path: path.stat().st_mtime_ns, default=None)

    suffix = ".msgpack"
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
    "AudioIndexProgress",
    "AudioRef",
    "enumerate_audio_refs",
    "find_mapping",
    "inspect_shared_copies",
    "resolve_audio_refs",
    "resolve_audio_paths",
    "resolve_mapping_path",
]
