"""BIN 来源选择与基础数据构建辅助。

该模块负责按优先级从 WAD 或本地 BIN 输入目录提取 BIN 二进制数据，
并统一加载地图 BIN、生成带标准元数据的基础数据结构。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from league_tools.formats import BIN, WAD
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
    resource_v2: bool

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

    将 BIN 来源（WAD 优先、本地 BIN 回退）的解析逻辑集中在此，
    供英雄/地图处理器复用。
    """

    def __init__(  # noqa: PLR0913
        self,
        *,
        ctx: AppContext,
        game_path: Path,
        version: str,
        local_bin_input_dir: Path,
        use_local_bin_flag_file: Path,
        languages: list[str] | None = None,
    ):
        """初始化 BIN 来源。

        :param ctx: 运行时上下文。
        :param game_path: 游戏客户端根目录。
        :param version: 当前游戏版本。
        :param local_bin_input_dir: 本地 BIN 输入目录。
        :param use_local_bin_flag_file: 本地 BIN 模式标志文件路径。
        :param languages: 元数据语言列表，在 update() 中初始化。
        """
        self.ctx = ctx
        self.game_path = game_path
        self.version = version
        self.local_bin_input_dir = local_bin_input_dir
        self.use_local_bin_flag_file = use_local_bin_flag_file
        self.languages: list[str] = languages if languages is not None else []
        self._wad_index: WadIndex | None = None

    def _is_dev_mode(self) -> bool:
        """返回当前运行是否为开发模式。"""
        return bool(self.ctx.config.dev_mode)

    def _is_local_bin_mode_enabled(self) -> bool:
        """
        检查是否启用了本地 BIN 输入模式。

        :returns: 启用返回 True，否则返回 False。
        """
        return self.use_local_bin_flag_file.exists()

    def _uses_resource_v2(self) -> bool:
        """判断当前来源是否允许创建 local resource schema v2。"""
        mode = getattr(self.ctx.config, "source_mode", "local_path")
        mode_value = getattr(mode, "value", mode)
        return mode_value != "remote_snapshot" and not self._is_local_bin_mode_enabled()

    def _build_local_bin_path(self, bin_path: str) -> Path:
        """
        将 binPath 转换为本地 BIN 文件绝对路径，并阻止路径逃逸。

        :param bin_path: 数据文件中的相对 BIN 路径。
        :returns: 本地 BIN 文件绝对路径。
        :raises ValueError: 当路径越界时抛出。
        """
        local_root = self.local_bin_input_dir.resolve()
        candidate = (self.local_bin_input_dir / Path(bin_path)).resolve()
        try:
            candidate.relative_to(local_root)
        except ValueError as e:
            raise ValueError(f"检测到越界 binPath，拒绝读取: {bin_path}") from e
        return candidate

    def _extract_bin_raws(
        self,
        wad_path: Path | None,
        bin_paths: list[str],
        entity_label: str,
        local_required_dir: Path | None = None,
    ) -> list[bytes | None]:
        """
        按优先级提取 BIN 二进制数据。

        优先级:
        1) WAD 文件存在时，强制走 WAD 提取。
        2) WAD 不存在时，若存在 `.use_local_bin` 标志，则走本地目录读取。
        3) 其余情况返回空结果。

        :param wad_path: 待提取的 WAD 路径；为空表示无可用 WAD 信息。
        :param bin_paths: 目标 BIN 路径列表。
        :param entity_label: 实体标签（用于日志）。
        :param local_required_dir: 本地模式下要求存在的目录（相对于 `bin_input`）。
        :returns: 与 `bin_paths` 顺序一致的二进制数组，缺失项为 ``None``。
        :raises FileNotFoundError: 本地模式开启但目录缺失时抛出。
        :raises ValueError: 当路径越界时抛出。
        """
        if not bin_paths:
            return []

        if wad_path and wad_path.exists():
            logger.trace(f"{entity_label} 使用 WAD 读取 BIN: {wad_path}")
            return WAD(wad_path).extract(bin_paths, raw=True)

        if not self._is_local_bin_mode_enabled():
            if wad_path:
                logger.warning(f"{entity_label} 的WAD文件不存在，且未启用本地BIN模式: {wad_path}")
            else:
                logger.warning(f"{entity_label} 缺少WAD路径信息，且未启用本地BIN模式")
            return []

        if wad_path:
            logger.debug(f"{entity_label} 的WAD文件不可用，回退到本地BIN模式: {wad_path}")
        else:
            logger.debug(f"{entity_label} 缺少WAD路径信息，回退到本地BIN模式")

        if not self.local_bin_input_dir.exists():
            raise FileNotFoundError(f"{entity_label} 启用了本地BIN模式，但目录不存在: {self.local_bin_input_dir}")

        if local_required_dir is not None:
            required_path = self.local_bin_input_dir / local_required_dir
            if not required_path.exists():
                raise FileNotFoundError(f"{entity_label} 本地BIN实体目录不存在: {required_path}")

        bin_raws: list[bytes | None] = []
        missing_count = 0
        for bin_path in bin_paths:
            local_bin_file = self._build_local_bin_path(bin_path)
            if not local_bin_file.is_file():
                bin_raws.append(None)
                missing_count += 1
                continue

            file_data = local_bin_file.read_bytes()
            if not file_data:
                bin_raws.append(None)
                missing_count += 1
                continue
            bin_raws.append(file_data)

        if missing_count > 0:
            logger.debug(f"{entity_label} 本地BIN存在缺失或空文件，已按缺失处理: {missing_count}/{len(bin_paths)}")

        logger.trace(f"{entity_label} 使用本地BIN目录读取: {self.local_bin_input_dir}")
        return bin_raws

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
        *,
        local_required_dir: Path | None = None,
    ) -> BinBatch:
        """按 source contract 读取 declared BIN 并生成 local v2 bindings。

        `.use_local_bin` 代表 remote snapshot 已准备好的旧合同，必须在构造本地索引前
        短路。普通本地客户端则统一从 FINAL TOC 解析真实物理 WAD。
        """
        if not bin_paths:
            return BinBatch(raws={}, bindings=[], resource_v2=self._uses_resource_v2())

        if self._is_local_bin_mode_enabled():
            raw_values = self._extract_bin_raws(
                wad_path=None,
                bin_paths=bin_paths,
                entity_label=entity_label,
                local_required_dir=local_required_dir,
            )
            raws = {path: raw for path, raw in zip(bin_paths, raw_values, strict=False) if raw is not None}
            return BinBatch(raws=raws, bindings=[], resource_v2=False)

        if not self._uses_resource_v2():
            logger.warning(f"{entity_label} 的 remote BIN 输入尚未准备完成，跳过本地 WAD resolver")
            return BinBatch(raws={}, bindings=[], resource_v2=False)

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
        return BinBatch(raws=raws, bindings=bindings, resource_v2=True)

    def _resolve_bank_bindings(self, references: list[BankReference]) -> list[BankBinding]:
        """把已解析 BIN 中的 bank 声明批量解析为物理 WAD bindings。"""
        if not references or not self._uses_resource_v2():
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
        """加载地图 BIN，并保留 v2 binding 或 remote 旧合同诊断。"""
        bin_path = map_data.get("binPath")
        if not bin_path:
            return LoadedBin(None, BinBatch({}, [], self._uses_resource_v2()))

        local_required_dir = Path(bin_path).parent
        batch = BinBatch({}, [], self._uses_resource_v2())
        try:
            batch = self._resolve_bin_resources(
                [bin_path],
                f"地图 {map_id}",
                local_required_dir=local_required_dir,
            )
            if not (bin_raw := batch.raws.get(bin_path)):
                return LoadedBin(None, batch)
            try:
                return LoadedBin(BIN(bin_raw), batch)
            except Exception:
                batch.mark_parse_failed(bin_path, "BIN 内容解析失败")
                raise
        except (FileNotFoundError, ValueError):
            logger.opt(exception=True).error(f"提取或解析地图 {map_id} 的本地BIN文件时出错")
        except Exception:
            logger.opt(exception=True).error(f"提取或解析地图 {map_id} 的BIN文件时出错")
            if self._is_dev_mode():
                raise
        return LoadedBin(None, batch)

    def _load_map_bin_file(self, map_id: str, map_data: dict) -> BIN | None:
        """
        统一加载地图 BIN 文件，兼容 WAD 与本地 BIN 模式。

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
