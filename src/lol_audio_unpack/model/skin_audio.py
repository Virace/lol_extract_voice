"""从精确资源声明派生英雄皮肤的共享归属，保留原始 binding 不变。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from lol_audio_unpack.model.binding import SUCCESS_STATUSES

if TYPE_CHECKING:
    from lol_audio_unpack.model.entity import AudioBank

CategoryKey = tuple[str, str]
ResourceKey = tuple[str, str, str, str]
SKIN_AUDIO_VERSION = 1


def bank_identity(bank: AudioBank) -> ResourceKey:
    """返回含音频类型的物理容器身份，不以分类名称或 WEM ID 判断共享。"""
    binding = bank.binding
    return bank.audio_type, (binding.wad or "").casefold(), binding.entry_hash.casefold(), binding.kind


class SkinAudio:
    """在单个英雄内确定规范输出归属和分类共享来源。

    Args:
        banks: 完整的皮肤资源声明，包括失败项。
        parents: 结构化数据中的基础皮肤与炫彩父级关系。
    """

    def __init__(self, banks: tuple[AudioBank, ...], parents: Mapping[str, str | None]) -> None:
        """建立当前英雄的分类、物理容器归属与父级索引。"""
        self.groups: dict[CategoryKey, list[AudioBank]] = {}
        self._owners: dict[ResourceKey, AudioBank] = {}
        self._parents = parents
        # 父级始终先于后代；同源资源在无直接父级关系时按稳定 ID 归属，避免执行顺序改变路径。
        ordered = sorted(
            banks,
            key=lambda bank: (self._sort_key(bank.sub_id), bank.binding.category, bank.binding.normalized_path),
        )
        for bank in ordered:
            self.groups.setdefault((bank.sub_id, bank.binding.category), []).append(bank)
            if self._resolved(bank):
                self._owners.setdefault(bank_identity(bank), bank)

    def _sort_key(self, sub_id: str) -> tuple[int, int, str]:
        depth = 0
        seen = {sub_id}
        parent = self._parents.get(sub_id)
        while parent is not None and parent not in seen:
            seen.add(parent)
            depth += 1
            parent = self._parents.get(parent)
        return depth, int(sub_id) if sub_id.isdecimal() else 0, sub_id

    @staticmethod
    def _resolved(bank: AudioBank) -> bool:
        return bank.binding.status in SUCCESS_STATUSES and bool(bank.binding.wad)

    def owner(self, bank: AudioBank) -> AudioBank:
        """返回同源容器的规范声明；未解析资源保持原归属。"""
        return self._owners.get(bank_identity(bank), bank) if self._resolved(bank) else bank

    def output_banks(self) -> tuple[AudioBank, ...]:
        """返回只落盘一次的容器及所有失败声明，保留完整度诊断。"""
        unresolved = tuple(bank for banks in self.groups.values() for bank in banks if not self._resolved(bank))
        return (*self._owners.values(), *unresolved)

    def sources(self, key: CategoryKey) -> tuple[CategoryKey, ...]:
        """返回当前分类实际复用的规范来源分类，不猜测未解析项。"""
        sources = {
            (owner.sub_id, owner.binding.category)
            for bank in self.groups.get(key, ())
            if self._resolved(bank) and (owner := self.owner(bank)).sub_id != key[0]
        }
        return tuple(sorted(sources, key=lambda source: (self._sort_key(source[0]), source[1])))

    def is_shared(self, key: CategoryKey) -> bool:
        """判断分类是否全部已解析且完全共享；失败或空声明不能证明共享。"""
        banks = self.groups.get(key, ())
        return bool(banks) and all(self._resolved(bank) and self.owner(bank).sub_id != key[0] for bank in banks)

    def is_complete(self, key: CategoryKey) -> bool:
        """判断分类的每条物理声明是否均可用于差异判断。"""
        banks = self.groups.get(key, ())
        return bool(banks) and all(self._resolved(bank) for bank in banks)

    def shared_payload(self) -> dict[str, dict[str, dict]]:
        """导出共享来源与完整度，供 mapping、原始数据和资源信息追溯。"""
        result: dict[str, dict[str, dict]] = {}
        for key in self.groups:
            sources = self.sources(key)
            if not sources:
                continue
            state = "shared" if self.is_shared(key) else "mixed" if self.is_complete(key) else "unknown"
            result.setdefault(key[0], {})[key[1]] = {
                "status": state,
                "sources": [{"skinId": sub_id, "category": category} for sub_id, category in sources],
            }
        return result

    def mapping_differences(self, skins: Mapping[str, dict]) -> dict[str, dict]:
        """省略完全继承的事件，有变化的事件保留全部音频引用。

        展示去重以完整事件为单位；文件落盘归属独立处理。事件新增、替换或减少引用时都保留
        完整映射，共享媒体仍指向规范路径。分类不完整或来源无法确认时不省略事件。
        """
        result: dict[str, dict] = {}
        for sub_id, payload in skins.items():
            events: dict[str, dict] = {}
            paths: dict[str, dict] = {}
            for category, current in payload.get("events", {}).items():
                key = str(sub_id), category
                current_paths = payload.get("audioPaths", {}).get(category, {})
                inherited = [
                    skins.get(source_id, {}).get("events", {}).get(source_category, {})
                    for source_id, source_category in self.sources(key)
                ]
                inherited_paths = [
                    skins.get(source_id, {}).get("audioPaths", {}).get(source_category, {})
                    for source_id, source_category in self.sources(key)
                ]
                for event, ids in current.items():
                    if self._is_inherited_event(
                        key,
                        event,
                        ids,
                        current_paths=current_paths,
                        inherited=inherited,
                        inherited_paths=inherited_paths,
                    ):
                        continue
                    if ids:
                        events.setdefault(category, {})[event] = list(ids)
                        if event in current_paths:
                            paths.setdefault(category, {})[event] = list(current_paths[event])
            if events:
                result[str(sub_id)] = {**payload, "events": events, "audioPaths": paths}
        return result

    def _is_inherited_event(  # noqa: PLR0913
        self,
        key: CategoryKey,
        event: str,
        ids: list,
        *,
        current_paths: dict,
        inherited: list[dict],
        inherited_paths: list[dict],
    ) -> bool:
        """只有同名事件的完整 ID 集合与精确文件引用均相同时，才视为纯继承。"""
        paths = current_paths.get(event)
        source_ids = {str(value) for events in inherited for value in events.get(event, ())}
        if not self.is_complete(key) or not source_ids or {str(value) for value in ids} != source_ids:
            return False
        source_paths = {path for events in inherited_paths for path in events.get(event, ())}
        if paths is not None or source_paths:
            return bool(paths) and set(paths) == source_paths
        # 没有落盘文件时，只有容器完全共享才能证明相同 ID 引用了相同媒体。
        return self.is_shared(key)
