"""WAV 当前输出记录与单任务内的内容归并。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from ...app.resource_pack import parse_resource_pack_key
from ...app.types import WavOutputOptions
from ..library import Library, WavRef


@dataclass(frozen=True)
class CacheInput:
    """一次实际输入的内容身份和对应当前可用输出。"""

    source: Path
    digest: str
    cached: Path | None = None


class WavCache:
    """只记录固定可见文件的当前格式，不保存多方案或多版本 WAV 缓存。"""

    def __init__(
        self, options: WavOutputOptions, root: Path | None = None, version: str | None = None, region: str | None = None
    ):
        self.format = options.format.strip().lower()
        self.library = Library(root) if root is not None and version and region else None
        self.version, self.region = version, region
        self.index = self.library.load(version, region) if self.library else None
        self.completed: dict[str, WavRef] = {}

    def identify(self, source: Path) -> CacheInput:
        """按来源实体和 ID 查询摘要；独立输入仅在实际转码时读取内容。"""
        source = source.resolve()
        digest = None
        if self.index is not None and source.suffix.lower() == ".wem":
            parts = source.relative_to(self.library.root).parts
            groups = {"champions": "champion", "maps": "map", "resource_packs": "resource_pack"}
            for i, part in enumerate(parts):
                if part in groups:
                    entity_id = unquote(parts[i + 1].split("·", 1)[0])
                    if part == "resource_packs":
                        entity_id = parse_resource_pack_key(entity_id).value
                    skin_id = parts[i + 2].split("·", 1)[0] if part == "champions" else None
                    digest = self.index.find_media(groups[part], entity_id, int(source.stem), skin_id)
                    break
            if digest is None:
                raise ValueError(f"内容索引没有此实体的 WEM ID: {source}")
        if digest is None:
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
        cached = None
        if self.library is not None and source.suffix.lower() == ".wem":
            relative = source.relative_to(self.library.root)
            output = Path("wavs", *relative.parts[1:]).with_suffix(".wav")
            record = self.index.find_wav(output.as_posix())
            if record == {"digest": digest, "format": self.format}:
                candidate = self.library.resolve(output.as_posix())
                if candidate.is_file():
                    cached = candidate
        return CacheInput(source, digest, cached)

    def record(self, digest: str, output: Path) -> None:
        """输出成功替换后保存当前状态；一次输出路径只保留一条记录。"""
        if self.library is not None:
            relative = output.relative_to(self.library.root).as_posix()
            self.completed[relative] = WavRef(relative, digest, self.format)

    def commit(self, writer: Library | None) -> None:
        """批次完成后原子归并当前输出信息。"""
        if writer is not None and self.completed:
            writer.merge(self.version, self.region, wavs=self.completed.values())
            self.index = writer.load(self.version, self.region)
            self.completed.clear()
