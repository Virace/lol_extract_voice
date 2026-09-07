"""单实体音频导出的紧凑范围与路径边界。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from lol_audio_unpack.manager.files import read_data

from .mapping_preview import normalize_mapping

_EVENT_KEY_SIZE = 3


def _relative(value: str) -> str:
    """拒绝跨目录与绝对引用，统一可序列化的相对键。"""
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or ":" in value:
        raise ValueError(f"音频引用必须位于当前实体目录内: {value}")
    return path.as_posix()


@dataclass(frozen=True, slots=True)
class MappingNode:
    """引用同一版映射中的稳定分组、类型或事件，不携带逐文件清单。"""

    mapping_path: Path
    entity_type: str
    entity_id: str
    signature: tuple[int, int]
    key: tuple[str, ...] = ()
    prefix: str = ""

    def resolve_paths(self, cache: dict[tuple[Path, tuple[int, int]], dict]) -> tuple[str, ...]:
        """后台复核映射未变化，再解析节点内的精确路径。"""
        cache_key = self.mapping_path, self.signature
        if cache_key not in cache:
            stat = self.mapping_path.stat()
            if (stat.st_size, stat.st_mtime_ns) != self.signature:
                raise ValueError("所选节点的映射已变化，请重新加载并核对选择")
            cache[cache_key] = (
                normalize_mapping(read_data(self.mapping_path), entity_type=self.entity_type, entity_id=self.entity_id)
                or {}
            )
        mapping = cache[cache_key]
        groups = next(
            (mapping[key] for key in ("skins", "map", "resourcePacks") if isinstance(mapping.get(key), dict)), {}
        )
        group = next((value for key, value in groups.items() if str(key) == self.key[0]), None)
        if not isinstance(group, dict):
            raise ValueError("原映射节点不可用，请重新加载并核对选择")
        paths = []
        for kind, events in group.get("events", {}).items():
            if len(self.key) > 1 and str(kind) != self.key[1]:
                continue
            for event, audio_ids in events.items():
                if len(self.key) == _EVENT_KEY_SIZE and str(event) != self.key[2]:
                    continue
                ids = {str(value).strip() for value in audio_ids}
                values = group.get("audioPaths", {}).get(kind, {}).get(event, ())
                for value in values:
                    logical = _relative(str(value))
                    if PurePosixPath(logical).stem not in ids:
                        continue
                    if self.prefix:
                        if not logical.startswith(self.prefix + "/"):
                            continue
                        logical = logical[len(self.prefix) + 1 :]
                    paths.append(logical)
        return tuple(dict.fromkeys(paths))


@dataclass(frozen=True, slots=True)
class AudioScope:
    """记录目录、精确文件和排除项，不为全选建立逐文件快照。

    Attributes:
        root: 领域层提供的当前实体音频目录。
        directories: 相对目录；``.`` 表示整个实体。
        files: 精确 WEM 相对路径，即使执行时消失也须报告失败。
        excluded: 在已选范围中排除的精确路径。
    """

    root: Path
    directories: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    excluded: frozenset[str] = frozenset()
    nodes: tuple[MappingNode, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", Path(self.root).expanduser().absolute())
        for name in ("directories", "files"):
            object.__setattr__(self, name, tuple(dict.fromkeys(_relative(value) for value in getattr(self, name))))
        object.__setattr__(self, "excluded", frozenset(_relative(value) for value in self.excluded))
        object.__setattr__(self, "nodes", tuple(self.nodes))

    def contains(self, relative_path: str) -> bool:
        """判断稳定引用是否在范围中；此判断不访问文件系统。"""
        key = _relative(relative_path)
        return key not in self.excluded and (
            key in self.files
            or any(directory == "." or key.startswith(directory + "/") for directory in self.directories)
        )

    def resolve_files(self) -> tuple[Path, ...]:
        """在后台枚举当前目录并校验边界，保留已确认但消失的精确文件。

        Returns:
            按物理路径去重的 WEM 文件；同 ID 不同路径保持独立。

        Raises:
            FileNotFoundError: 已选目录已经消失。
            ValueError: 引用或符号链接越出实体根目录。
        """
        root = self.root.resolve()
        candidates: dict[Path, None] = {}
        mapping_cache: dict[tuple[Path, tuple[int, int]], dict] = {}
        for node in self.nodes:
            # 节点只纳入现有文件，映射中的未解包项不自动变为解包任务。
            for key in node.resolve_paths(mapping_cache):
                candidate = root / key
                if candidate.is_file():
                    candidates[candidate] = None
        for directory in self.directories:
            folder = (root / directory).resolve()
            folder.relative_to(root)
            if not folder.is_dir():
                raise FileNotFoundError(f"所选音频目录不可用: {folder}")
            candidates.update(dict.fromkeys(folder.rglob("*.wem")))
        candidates.update(dict.fromkeys(root / key for key in self.files))
        sources: dict[Path, None] = {}
        for candidate in candidates:
            key = candidate.relative_to(root).as_posix()
            if key in self.excluded:
                continue
            resolved = candidate.resolve()
            resolved.relative_to(root)
            if resolved.suffix.lower() != ".wem":
                raise ValueError(f"所选文件不是 WEM: {key}")
            sources[resolved] = None
        return tuple(sources)
