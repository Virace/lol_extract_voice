"""BIN 来源选择与基础数据构建辅助。

该模块负责从本地 FINAL WAD 索引提取 BIN 二进制数据，
并统一加载地图 BIN、生成带标准元数据的基础数据结构。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from league_tools.formats import BIN
from loguru import logger

from lol_audio_unpack.manager.utils import build_metadata_payload
from lol_audio_unpack.model.binding import (
    SUCCESS_STATUSES,
    BankBinding,
    BankReference,
    BinBinding,
    BindingRole,
    BindingStatus,
)
from lol_audio_unpack.runtime.wad_index import ResolutionRequest, WadIndex, WadTocCache

if TYPE_CHECKING:
    from lol_audio_unpack.app.types import AppContext


_WAD_TOC_CACHE_KEY = "local_wad_toc_cache"


@dataclass
class BinBatch:
    """一次 declared BIN 批量读取结果。"""

    raws: dict[str, bytes]
    bindings: list[BinBinding]

    def mark_parse_failed(self, path: str, diagnostic: str) -> None:
        """把指定 BIN 的成功解析结果改记为内容解析失败。"""
        self.bindings = [
            replace(binding, status=BindingStatus.PARSE_FAILED, diagnostic=diagnostic)
            if binding.path == path and binding.status in SUCCESS_STATUSES
            else binding
            for binding in self.bindings
        ]


@dataclass
class LoadedBin:
    """单个 BIN 对象及其批量资源诊断。"""

    bin_file: BIN | None
    batch: BinBatch


class BinSource:
    """承载 BIN 提取/加载与基础数据构建职责。

    将本地 WAD 索引解析逻辑集中在此，供英雄/地图处理器复用。
    """

    def __init__(
        self,
        *,
        ctx: AppContext,
        game_path: Path,
        version: str,
        languages: list[str] | None = None,
    ):
        """初始化 BIN 来源。

        :param ctx: 运行时上下文。
        :param game_path: 游戏客户端根目录。
        :param version: 当前游戏版本。
        :param languages: 元数据语言列表，在 update() 中初始化。
        """
        self.ctx = ctx
        self.game_path = game_path
        self.version = version
        self.languages: list[str] = languages if languages is not None else []
        self._wad_index: WadIndex | None = None

    def _is_dev_mode(self) -> bool:
        """返回当前运行是否为开发模式。"""
        return bool(self.ctx.config.dev_mode)

    def _get_wad_index(self) -> WadIndex:
        """延迟创建并在当前运行中共享本地 WAD TOC cache。"""
        if index := getattr(self, "_wad_index", None):
            return index

        cache = self.ctx.runtime_cache.get(_WAD_TOC_CACHE_KEY)
        if cache is None:
            cache = WadTocCache()
            self.ctx.runtime_cache[_WAD_TOC_CACHE_KEY] = cache
        self._wad_index = WadIndex(self.game_path, self.ctx.config.game_region, cache=cache)
        return self._wad_index

    def _resolve_bin_resources(
        self,
        bin_paths: list[str],
        entity_label: str,
    ) -> BinBatch:
        """从本地 FINAL TOC 读取 declared BIN 并生成 v2 bindings。"""
        if not bin_paths:
            return BinBatch(raws={}, bindings=[])

        logger.trace(f"{entity_label} 通过 FINAL WAD 索引解析 {len(bin_paths)} 个 BIN")
        resolutions = self._get_wad_index().resolve_many(
            [ResolutionRequest(path, preferred_role=BindingRole.ROOT) for path in bin_paths],
            load_payload=True,
        )
        bindings = [
            BinBinding(
                path=result.path,
                normalized_path=result.normalized_path,
                wad=result.wad,
                entry_hash=result.entry_hash,
                status=result.status,
                role=result.role,
                candidates=result.candidates if len(result.candidates) > 1 else (),
                diagnostic=result.diagnostic,
            )
            for result in resolutions
        ]
        raws = {
            result.path: result.payload
            for result in resolutions
            if result.status in SUCCESS_STATUSES and result.payload is not None
        }
        return BinBatch(raws=raws, bindings=bindings)

    def _resolve_bank_bindings(self, references: list[BankReference]) -> list[BankBinding]:
        """把已解析 BIN 中的 bank 声明批量解析为物理 WAD bindings。"""
        if not references:
            return []

        results = self._get_wad_index().resolve_many(
            [ResolutionRequest(reference.path, reference.preferred_role) for reference in references]
        )
        return [
            BankBinding(
                category=reference.category,
                path=reference.path,
                normalized_path=result.normalized_path,
                kind="",
                wad=result.wad,
                entry_hash=result.entry_hash,
                source_bin=reference.source_bin,
                role=result.role,
                status=result.status,
                sub_entity=reference.sub_entity,
                group=reference.group,
                candidates=result.candidates if len(result.candidates) > 1 else (),
                diagnostic=result.diagnostic,
            )
            for reference, result in zip(references, results, strict=True)
        ]

    def _resource_index_diagnostics(self) -> tuple[dict, list[str]]:
        """返回当前实体可写入 artifact 的累计索引指标与错误。"""
        index = getattr(self, "_wad_index", None)
        if index is None:
            return {}, []
        return index.snapshot_metrics(), list(index.errors)

    def _load_map_bin_resource(self, map_id: str, map_data: dict) -> LoadedBin:
        """加载地图 BIN，并保留 v2 binding 诊断。"""
        bin_path = map_data.get("binPath")
        if not bin_path:
            return LoadedBin(None, BinBatch({}, []))

        batch = BinBatch({}, [])
        try:
            batch = self._resolve_bin_resources(
                [bin_path],
                f"地图 {map_id}",
            )
            if not (bin_raw := batch.raws.get(bin_path)):
                return LoadedBin(None, batch)
            try:
                return LoadedBin(BIN(bin_raw), batch)
            except Exception:
                batch.mark_parse_failed(bin_path, "BIN 内容解析失败")
                raise
        except (FileNotFoundError, ValueError):
            logger.opt(exception=True).error(f"从本地 WAD 提取或解析地图 {map_id} 的 BIN 文件时出错")
        except Exception:
            logger.opt(exception=True).error(f"提取或解析地图 {map_id} 的BIN文件时出错")
            if self._is_dev_mode():
                raise
        return LoadedBin(None, batch)

    def _load_map_bin_file(self, map_id: str, map_data: dict) -> BIN | None:
        """从本地 WAD 索引加载地图 BIN 文件。

        :param map_id: 地图ID。
        :param map_data: 地图数据字典。
        :returns: BIN 对象；失败时返回 None。
        """
        return self._load_map_bin_resource(map_id, map_data).bin_file

    def _create_base_data(self, entity_id: str, entity_type: str, **extra_fields) -> dict:
        """
        创建包含元数据和实体特定信息的基础数据结构。

        :param entity_id: 实体ID（英雄ID或地图ID）
        :param entity_type: 实体类型（'champion' 或 'map'）
        :param extra_fields: 任何要添加到顶层的额外字段
        :return: 包含元数据和附加字段的基础字典
        """
        # 使用通用函数创建包含所有标准元数据的对象
        base_data = build_metadata_payload(self.version, self.languages)

        # 检查是否为事件文件（通过是否存在'skins'或'map'顶级键来判断）
        is_event_file = "skins" in extra_fields or "map" in extra_fields

        # 如果是事件文件，则从中移除 'languages' 字段
        if is_event_file and "metadata" in base_data and "languages" in base_data["metadata"]:
            del base_data["metadata"]["languages"]

        # 添加实体特定ID
        if entity_type == "champion":
            base_data["championId"] = entity_id
        elif entity_type == "map":
            base_data["mapId"] = entity_id

        # 合并任何其他的附加字段
        base_data.update(extra_fields)
        return base_data
