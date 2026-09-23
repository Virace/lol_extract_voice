"""解包结果中的成功路径清单；与 WEM 内容索引和事件映射独立。"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from urllib.parse import unquote

import msgpack

from lol_audio_unpack.runtime.library.types import normalize_region, relative_path
from lol_audio_unpack.utils.atomic import replace_file

from .path_layout import get_entity_path_component, get_output_dir_name


def output_path(root: Path, version: str, region: str, entity_type: str, entity_id: str) -> Path:
    """定位一个实体的成功路径清单，不探测音频目录。"""
    component = get_entity_path_component(entity_type, entity_id)
    return (
        root
        / "reports"
        / relative_path(version)
        / normalize_region(region)
        / get_output_dir_name(entity_type)
        / f"{component}.audios.msgpack"
    )


def split_audio(path: Path) -> tuple[Path, str, str | None, str | None]:
    """从标准可见路径拆分实体根、逻辑路径、类型和子实体。"""
    parts = path.parts
    group = next(i for i, part in enumerate(parts) if part in {"champions", "maps", "resource_packs"})
    root = Path(*parts[: group + 2])
    tail = parts[group + 2 :]
    grouped = parts[group - 1] in {"VO", "SFX", "MUSIC"}
    logical = Path(parts[group - 1], *tail) if grouped else Path(*tail)
    audio_type = parts[group - 1] if grouped else (tail[-2] if len(tail) > 1 else "")
    sub_id = tail[0].split("·", 1)[0] if parts[group] == "champions" and audio_type != "lobby" else None
    if parts[group] != "champions":
        sub_id = unquote(parts[group + 1].split("·", 1)[0])
    return root, logical.as_posix(), audio_type.upper() or None, sub_id


def load_outputs(root: Path, version: str, region: str, entity_type: str, entity_id: str) -> tuple[Path, ...]:
    """仅在请求全部音频时读取当前实体成功路径，不逐文件检查。"""
    path = output_path(root, version, region, entity_type, entity_id)
    if not path.is_file():
        return ()
    payload = msgpack.unpackb(path.read_bytes(), raw=False)
    return tuple(root / relative_path(value) for value in payload["files"])


def output_summary(
    root: Path, version: str, region: str, entity_type: str, entity_id: str
) -> tuple[int, tuple[Path, ...]]:
    """读取清单头的计数与根目录，文件列表保持未解码。"""
    path = output_path(root, version, region, entity_type, entity_id)
    if not path.is_file():
        return 0, ()
    with path.open("rb") as stream:
        unpacker = msgpack.Unpacker(stream, raw=False)
        if unpacker.read_map_header() != 3 or unpacker.unpack() != "count":  # noqa: PLR2004
            raise ValueError(f"音频清单头无效: {path}")
        count = unpacker.unpack()
        if unpacker.unpack() != "roots":
            raise ValueError(f"音频清单根目录无效: {path}")
        roots = tuple(root / relative_path(value) for value in unpacker.unpack())
    return count, roots


def save_outputs(  # noqa: PLR0913, PLR0917
    root: Path, version: str, region: str, entity_type: str, entity_id: str, paths: Iterable[Path]
) -> None:
    """合入已成功落盘的路径；部分重试、筛选和取消不删除其他成功记录。"""
    root = root.resolve()
    files = set(load_outputs(root, version, region, entity_type, entity_id))
    files.update(paths)
    roots = sorted({split_audio(path)[0].relative_to(root).as_posix() for path in files})
    payload = {
        "count": len(files),
        "roots": roots,
        "files": sorted(path.relative_to(root).as_posix() for path in files),
    }
    target = output_path(root, version, region, entity_type, entity_id)
    replace_file(
        target, lambda temp: temp.write_bytes(msgpack.packb(payload, use_bin_type=True)), write_stage="outputs"
    )


def managed_files(folder: Path) -> tuple[Path, ...] | None:
    """从管理目录的实体清单筛选文件；外部独立目录返回 None。"""
    parts = folder.parts
    if "audios" not in parts:
        return None
    offset = parts.index("audios")
    if len(parts) < offset + 3:
        return None
    root = Path(*parts[:offset])
    version, region = parts[offset + 1 : offset + 3]
    normalize_region(region)
    report = root / "reports" / version / region
    groups = {"champions": "champion", "maps": "map", "resource_packs": "resource_pack"}
    tail = parts[offset + 3 :]
    group = next((part for part in tail if part in groups), None)
    catalogs = []
    if group is not None and tail.index(group) + 1 < len(tail):
        entity_id = unquote(tail[tail.index(group) + 1].split("·", 1)[0])
        catalogs.append(output_path(root, version, region, groups[group], entity_id))
    else:
        for name in [group] if group else groups:
            catalogs.extend((report / name).glob("*.audios.msgpack"))
    files = []
    for catalog in catalogs:
        if not catalog.is_file():
            continue
        payload = msgpack.unpackb(catalog.read_bytes(), raw=False)
        files.extend(path for value in payload["files"] if (path := root / relative_path(value)).is_relative_to(folder))
    return tuple(files)
