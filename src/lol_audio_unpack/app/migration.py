"""将旧输出一次性搬入内容库，完成后只保留新目录与索引。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from urllib.parse import unquote

import msgpack
from loguru import logger
from ruamel.yaml import YAML

from lol_audio_unpack.model.progress import OperationProgress
from lol_audio_unpack.runtime.library import Library, LibraryError, MediaRef, ObjectRef
from lol_audio_unpack.runtime.library.types import normalize_region
from lol_audio_unpack.utils.atomic import replace_file

from .outputs import save_outputs
from .resource_pack import parse_resource_pack_key

_FORMATS = {".msgpack", ".json", ".yaml", ".yml"}
_PROGRESS_INTERVAL = 0.25
_TYPES = {"VO", "SFX", "MUSIC"}
_GROUPS = {"champions": "champion", "maps": "map", "resource_packs": "resource_pack"}
_SCOPES = {
    "manifest": {"banks", "events", "lobby", "lobby_vo", "unknown-category.txt"},
    "audios": {*_GROUPS, *_TYPES},
    "wavs": {*_GROUPS, *_TYPES},
    "hashes": {*_GROUPS, "integrated"},
    "reports": {*_GROUPS, "operations"},
}


@dataclass(frozen=True)
class _Move:
    """单个旧文件的目标与发布内容；旧文件保留到索引提交完成。"""

    source: Path
    target: Path
    digest: str
    stamp: tuple[int, int]
    payload: bytes | None = None
    media: MediaRef | None = None


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        result = hashlib.sha256()
        while chunk := stream.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def _read(path: Path) -> dict:
    """仅在一次性迁移中读取旧结构化格式，正常运行仍只读 MessagePack。"""
    if path.suffix == ".msgpack":
        value = msgpack.unpackb(path.read_bytes(), raw=False, strict_map_key=False)
    elif path.suffix == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
    else:
        value = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise LibraryError(f"旧元数据不是字典: {path}")
    return value


def _plain(path: Path, root: Path) -> None:
    """迁移不沿符号链接或 junction 移动库外文件。"""
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
            raise LibraryError(f"旧目录包含重解析点，未迁移: {current}")


def _walk(path: Path, root: Path):
    _plain(path, root)
    if path.is_dir():
        for child in sorted(path.iterdir()):
            yield from _walk(child, root)
        yield path
    elif path.is_file():
        yield path


def _media(path: Path, obj: ObjectRef) -> MediaRef:
    """从旧媒体目录恢复原归属，不需要 BIN、BNK 或 WPK 来源。"""
    parts = list(path.parts)
    grouped = parts[0] in _TYPES
    audio_type = parts.pop(0) if grouped else parts.pop(-2)
    group, folder, *tail = parts
    entity_type = _GROUPS[group]
    entity_id = folder.split("·", 1)[0]
    if entity_type == "resource_pack":
        entity_id = parse_resource_pack_key(unquote(entity_id)).value
    elif not entity_id.isdigit():
        raise LibraryError(f"旧媒体实体 ID 无效: {path}")
    if entity_type == "champion":
        skin, filename = tail
        skin_id = skin.split("·", 1)[0]
    else:
        (filename,) = tail
        skin_id = None
    if audio_type not in _TYPES or not Path(filename).stem.isdigit():
        raise LibraryError(f"旧媒体类型或原 ID 无效: {path}")
    return MediaRef(entity_type, entity_id, int(Path(filename).stem), obj, skin_id)


def _same(path: Path, digest: str) -> None:
    """目标已存在时只接纳相同内容，不用旧数据覆盖新数据。"""
    if path.exists() and (not path.is_file() or _digest(path) != digest):
        raise LibraryError(f"迁移目标已存在不同内容，旧文件未删除: {path}")


def _collect(writer: Library, marker: Path | None, version: str, region: str) -> tuple[list[_Move], list[Path]]:
    """先核对本版本全部目标，再发布链接，避免冲突时继续启动解包。"""
    root = writer.root
    sources = []
    directories = []
    for section, names in _SCOPES.items():
        base = root / section / version
        for name in sorted(names):
            scope = base / name
            if scope.exists():
                for path in _walk(scope, root):
                    (directories if path.is_dir() else sources).append(path)
    if marker is not None:
        sources.append(marker)
    moves = []
    index = writer.load(version, region)
    refs = {}
    targets = {}
    for source in sources:
        _plain(source, root)
        section, _, *parts = source.relative_to(root).parts
        target = writer.resolve((Path(section) / version / region / Path(*parts)).as_posix())
        stat = source.stat()
        payload = None
        media = None
        if section in {"manifest", "hashes"} and source.suffix in _FORMATS:
            payload = msgpack.packb(_read(source), use_bin_type=True)
            target = target.with_suffix(".msgpack")
        digest = hashlib.sha256(payload).hexdigest() if payload is not None else _digest(source)
        if section == "audios" and source.suffix == ".wem":
            media = _media(Path(*parts), ObjectRef(digest, stat.st_size))
            key = (media.entity_type, media.entity_id, media.media_id, media.skin_id)
            previous = refs.setdefault(key, index.find_media(*key) or digest)
            if previous != digest:
                raise LibraryError(f"相同媒体归属已有不同内容，旧文件未删除: {source}")
        _same(target, digest)
        previous_digest = targets.setdefault(target, digest)
        if previous_digest != digest:
            raise LibraryError(f"旧文件指向相同目标但内容不同: {source}")
        moves.append(_Move(source, target, digest, (stat.st_size, stat.st_mtime_ns), payload, media))
    return moves, directories


def _migrate(writer: Library, version: str, marker: Path | None, region: str, progress: Callable | None) -> None:
    root = writer.root
    if marker is not None:
        _plain(marker, root)
        metadata = _read(marker).get("metadata", {})
        languages = metadata.get("languages", [])
        regions = {normalize_region(value) for value in languages if value != "default"}
        if len(regions) > 1:
            raise LibraryError(f"旧库语言归属不唯一，未移动文件: {marker}")
        if regions:
            region = regions.pop()
    region = normalize_region(region)
    logger.info("开始迁移旧音频目录：{}/{}", version, region)
    if progress:
        progress(OperationProgress("migration", "library_migration", "started"))
    moves, directories = _collect(writer, marker, version, region)
    last = 0.0
    for number, move in enumerate(moves, 1):
        source, target = move.source, move.target
        if move.media is not None:
            archive = move.media.object.path
            _same(writer.resolve(archive), move.digest)
            if not writer.resolve(archive).exists():
                writer.link_file(source, archive)
            writer.link_file(writer.resolve(archive), target.relative_to(root).as_posix())
        elif not target.exists():
            if move.payload is not None:
                replace_file(
                    target, lambda temp, payload=move.payload: temp.write_bytes(payload), write_stage="migration"
                )
            else:
                writer.link_file(source, target.relative_to(root).as_posix())
        now = monotonic()
        if now - last >= _PROGRESS_INTERVAL or number == len(moves):
            if progress:
                progress(OperationProgress("migration", "library_migration", "advanced", number, len(moves)))
            last = now
    media = [move.media for move in moves if move.media is not None]
    writer.merge(version, region, media)
    outputs = {}
    for move in moves:
        if move.media is not None:
            key = (move.media.entity_type, move.media.entity_id)
        elif move.source.suffix.lower() == ".ogg":
            parts = move.target.relative_to(root).parts
            if parts[0] != "audios" or "champions" not in parts:
                continue
            folder = parts[parts.index("champions") + 1]
            key = ("champion", folder.split("·", 1)[0])
        else:
            continue
        outputs.setdefault(key, []).append(move.target)
    for (entity_type, entity_id), paths in outputs.items():
        save_outputs(root, version, region, entity_type, entity_id, paths)
    # 所有新链接与索引成功后才移除旧位置；data 标记最后删除，中断可按相同内容继续。
    for move in moves:
        stat = move.source.stat()
        if (stat.st_size, stat.st_mtime_ns) != move.stamp:
            raise LibraryError(f"迁移期间旧文件发生变化，未删除: {move.source}")
    for move in moves:
        move.source.unlink()
    for directory in directories:
        directory.rmdir()
    logger.success("旧音频目录迁移完成：{}/{}，{} 个文件，{} 条媒体引用", version, region, len(moves), len(media))
    if progress:
        progress(OperationProgress("migration", "library_migration", "finished", len(moves), len(moves)))


def migrate_library(root: Path, *, region: str = "en_US", progress_callback: Callable | None = None) -> None:
    """一次性迁移已有旧版输出，无游戏来源依赖，不保留旧目录读写分支。

    Args:
        root: 应用输出根目录。
        progress_callback: 后台调用方的结构化进度回调。

    Raises:
        LibraryError: 旧库不能确定归属，或新旧目标存在不同内容。
        OSError: 文件迁移失败；尚未删除的旧文件可在下次启动继续处理。
    """
    root = Path(root).resolve()
    versions = set()
    for section, names in _SCOPES.items():
        base = root / section
        if base.is_dir():
            versions.update(
                path.name
                for path in base.iterdir()
                if path.is_dir() and not path.name.startswith("_") and any((path / name).exists() for name in names)
            )
    manifest = root / "manifest"
    if manifest.is_dir():
        versions.update(path.parent.name for path in manifest.glob("*/data.*") if path.suffix in _FORMATS)
    if not versions:
        return
    try:
        with Library(root) as writer:
            for version in sorted(versions):
                markers = [path for path in (manifest / version).glob("data.*") if path.suffix in _FORMATS]
                if len(markers) > 1:
                    raise LibraryError(f"旧输出存在多个 data 元数据，请先明确来源: {manifest / version}")
                _migrate(writer, version, markers[0] if markers else None, region, progress_callback)
    except Exception:
        logger.exception("旧音频目录迁移未完成，停止新任务，保留尚未迁移的旧文件")
        raise
