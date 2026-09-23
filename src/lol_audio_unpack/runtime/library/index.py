"""单版本、单区域的 WEM 内容对应关系与当前 WAV 输出。"""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy

from .types import LibraryError, MediaRef, MergeResult, ObjectRef, WavRef, normalize_region, relative_path

SCHEMA = 2
GROUPS = {"champion": "champions", "map": "maps", "resource_pack": "resource_packs"}


class LibraryIndex:
    """保存内容与 ID，不参与事件映射、目录重建或源文件时效判断。"""

    def __init__(self, version: str, region: str, data: dict | None = None) -> None:
        self.version = relative_path(version)
        if "/" in self.version:
            raise LibraryError("版本必须是单个目录名")
        self.region = normalize_region(region)
        self._data = (
            deepcopy(data)
            if data is not None
            else {
                "schema": SCHEMA,
                "version": self.version,
                "algorithm": "sha256",
                "region": self.region,
                "champions": {},
                "maps": {},
                "resource_packs": {},
                "wavs": {},
            }
        )
        self._validate()

    @property
    def path(self) -> str:
        """返回此版本区域的唯一索引位置。"""
        return f"audios/_index/{self.version}/{self.region}.msgpack"

    def to_dict(self) -> dict:
        """返回可独立修改的序列化快照。"""
        return deepcopy(self._data)

    def iter_media(self):
        """按需遍历内容记录，供离线检查使用；正常浏览不调用。"""
        for entity_type, group in GROUPS.items():
            for entity_id, records in self._data[group].items():
                scopes = records.items() if entity_type == "champion" else ((None, records),)
                for skin_id, media in scopes:
                    for media_id, digest in media.items():
                        yield MediaRef(entity_type, entity_id, int(media_id), ObjectRef(digest), skin_id)

    def find_media(self, entity_type: str, entity_id: str, media_id: int, skin_id: str | None = None) -> str | None:
        """在实体与皮肤命名空间内查询 WEM 摘要，不访问文件系统。"""
        records = self._data[GROUPS[entity_type]].get(str(entity_id), {})
        if entity_type == "champion":
            records = records.get(str(skin_id), {})
        return records.get(str(media_id))

    def find_wav(self, path: str) -> dict | None:
        """查询固定输出位置当前对应的内容和格式。"""
        record = self._data["wavs"].get(path)
        return dict(record) if record is not None else None

    def merge(self, media: Iterable[MediaRef] = (), *, wavs: Iterable[WavRef] = ()) -> tuple[LibraryIndex, MergeResult]:
        """合入成功 WEM；同一 WAV 输出路径始终替换为最新成功记录。"""
        data = self.to_dict()
        added = updated = reused = 0
        incoming = {}
        for ref in media:
            key = (ref.entity_type, ref.entity_id, ref.skin_id, ref.media_id)
            digest = ref.object.digest
            if key in incoming and incoming[key] != digest:
                raise LibraryError(f"同一实体及皮肤内 WEM ID 对应不同内容: {key}")
            incoming[key] = digest
            records = data[GROUPS[ref.entity_type]].setdefault(ref.entity_id, {})
            if ref.entity_type == "champion":
                records = records.setdefault(ref.skin_id, {})
            previous = records.get(str(ref.media_id))
            reused += int(previous == digest)
            added += int(previous is None)
            updated += int(previous is not None and previous != digest)
            records[str(ref.media_id)] = digest
        for ref in wavs:
            data["wavs"][ref.path] = {"digest": ref.digest, "format": ref.format}
        return LibraryIndex(self.version, self.region, data), MergeResult(added, updated, reused, data != self._data)

    def _validate(self) -> None:
        """校验持久头与请求身份，拒绝把缺字段、损坏或旧实验格式当作空索引。"""
        try:
            data = self._data
            if set(data) != {"schema", "version", "algorithm", "region", *GROUPS.values(), "wavs"}:
                raise LibraryError("索引字段不完整或不受支持")
            if type(data["schema"]) is not int or data["schema"] != SCHEMA:
                raise LibraryError("索引 schema 不受支持")
            if (data["version"], data["region"], data["algorithm"]) != (self.version, self.region, "sha256"):
                raise LibraryError("索引版本、区域或摘要算法不匹配")
            for group in GROUPS.values():
                for entity_id, records in data[group].items():
                    if not isinstance(entity_id, str) or not entity_id:
                        raise LibraryError("实体 ID 无效")
                    scopes = records.items() if group == "champions" else ((None, records),)
                    for skin_id, media in scopes:
                        for media_id, digest in media.items():
                            if not isinstance(media_id, str) or not media_id.isdecimal():
                                raise LibraryError("WEM ID 无效")
                            entity_type = next(kind for kind, name in GROUPS.items() if name == group)
                            MediaRef(entity_type, entity_id, int(media_id), ObjectRef(digest), skin_id)
            for path, record in data["wavs"].items():
                if set(record) != {"digest", "format"}:
                    raise LibraryError("WAV 字段无效")
                WavRef(path, **record)
        except (KeyError, TypeError, AttributeError, ValueError) as exc:
            if isinstance(exc, LibraryError):
                raise
            raise LibraryError("索引结构损坏，拒绝覆盖") from exc
