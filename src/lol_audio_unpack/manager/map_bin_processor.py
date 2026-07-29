"""地图 BIN 链路处理。

负责按地图ID处理 BIN，提取 banks/events 数据，
并对非公共地图应用公共地图(ID 0)的去重逻辑。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from lol_audio_unpack.manager.bin_source import BinSource
from lol_audio_unpack.manager.files import needs_update, write_data
from lol_audio_unpack.utils.logging import performance_monitor
from lol_audio_unpack.utils.run_summary import record_runtime_note

if TYPE_CHECKING:
    from lol_audio_unpack.app.types import AppContext

# 类型别名定义
CommonEventSourceIndex = dict[str, set[str]]


class MapBinProcessor:
    """处理地图 BIN，生成 banks/events 数据并执行公共数据去重。"""

    def __init__(  # noqa: PLR0913
        self,
        bin_source: BinSource,
        *,
        ctx: AppContext,
        version: str,
        force_update: bool,
        process_events: bool,
        map_banks_dir: Path,
        map_events_dir: Path,
        languages: list[str] | None = None,
    ):
        """初始化地图 BIN 处理器。

        :param bin_source: BIN 来源辅助实例。
        :param ctx: 运行时上下文。
        :param version: 当前游戏版本。
        :param force_update: 是否强制更新，忽略版本检查。
        :param process_events: 是否处理事件数据。
        :param map_banks_dir: 地图 banks 输出目录。
        :param map_events_dir: 地图 events 输出目录。
        :param languages: 元数据语言列表，在 update() 中初始化。
        """
        self.bin_source = bin_source
        self.ctx = ctx
        self.version = version
        self.force_update = force_update
        self.process_events = process_events
        self.map_banks_dir = map_banks_dir
        self.map_events_dir = map_events_dir
        self.languages: list[str] = languages if languages is not None else []

    def _is_dev_mode(self) -> bool:
        """返回当前运行是否为开发模式。"""
        return bool(self.ctx.config.dev_mode)

    def _log_simple_progress(self, stage_name: str, index: int, total: int, entity_id: str) -> None:
        """输出简单的批量处理进度日志。"""
        logger.info(f"{stage_name}进度 {index}/{total}: {entity_id}")

    @performance_monitor(level="DEBUG")
    def _update_maps(self, data: dict) -> None:
        """
        处理地图数据，按地图ID分别生成文件

        :param data: 包含地图数据的字典
        """
        logger.info("开始处理地图音频数据...")
        self.map_banks_dir.mkdir(parents=True, exist_ok=True)
        self.map_events_dir.mkdir(parents=True, exist_ok=True)

        maps = data.get("maps", {})

        # 预处理公共地图(ID 0)的事件数据和Banks数据
        common_event_sources: CommonEventSourceIndex = {}
        common_banks_set = set()
        if "0" in maps:
            logger.debug("正在预处理公共地图(ID 0)的数据...")
            try:
                # 预处理事件数据
                if map_events := self._process_map_events_for_id("0", maps["0"]):
                    if "events" in map_events:
                        for category, events_list in map_events["events"].items():
                            for event_string in events_list:
                                common_event_sources.setdefault(event_string, set()).add(f"地图 0/{category}")

                # 预处理Banks数据
                if map_banks := self._process_map_banks_for_id("0", maps["0"]):
                    if "banks" in map_banks:
                        for paths_list in map_banks["banks"].values():
                            for path in paths_list:
                                common_banks_set.add(tuple(sorted(path)))
            except Exception:
                logger.opt(exception=True).error("预处理公共地图(ID 0)的数据时出错")
                if self._is_dev_mode():
                    raise

        map_items = list(maps.items())
        total_maps = len(map_items)
        for index, (map_id, map_data) in enumerate(map_items, start=1):
            self._log_simple_progress("处理地图", index, total_maps, map_id)
            self._process_single_map(map_id, map_data, common_event_sources, common_banks_set)

        logger.success(f"地图Banks数据更新完成，共处理 {total_maps} 个地图")

    def _process_single_map(
        self,
        map_id: str,
        map_data: dict,
        common_event_sources: CommonEventSourceIndex | None = None,
        common_banks_set: set | None = None,
    ) -> None:
        """
        处理单个地图的Banks和Events数据

        :param map_id: 地图ID
        :param map_data: 地图数据字典
        :param common_event_sources: 公共事件来源索引，用于事件去重和总结
        :param common_banks_set: 公共Banks集合，用于去重
        """
        banks_file_base = self.map_banks_dir / map_id
        events_file_base = self.map_events_dir / map_id

        if not needs_update(
            banks_file_base, self.version, self.force_update, dev_mode=self._is_dev_mode()
        ) and not needs_update(events_file_base, self.version, self.force_update, dev_mode=self._is_dev_mode()):
            logger.trace(f"地图 {map_id} 的数据已是最新，跳过处理")
            return

        if not map_data.get("binPath"):
            return

        bin_file = self.bin_source._load_map_bin_file(map_id, map_data)
        if bin_file is None:
            return

        # 处理Banks数据
        map_banks = {}
        for group in bin_file.data:
            for event_data in group.bank_units:
                if event_data.bank_path:
                    category = event_data.category
                    if category not in map_banks:
                        map_banks[category] = []
                    map_banks[category].append(event_data.bank_path)

        # 去重处理
        for category, paths in map_banks.items():
            unique_paths_tuples = dict.fromkeys(tuple(sorted(p)) for p in paths)
            map_banks[category] = [list(p) for p in unique_paths_tuples]

        # 写入Banks数据
        if map_banks and needs_update(banks_file_base, self.version, self.force_update, dev_mode=self._is_dev_mode()):
            map_banks_data = self.bin_source._create_base_data(
                map_id, "map", name=self._get_map_name(map_data), banks=map_banks
            )

            # 对非公共地图进行去重处理
            if map_id != "0" and common_banks_set:
                self._deduplicate_single_map_banks(map_banks_data, common_banks_set)

            # 去重后检查是否还有数据需要写入
            if map_banks_data.get("banks"):
                write_data(map_banks_data, banks_file_base, dev_mode=self._is_dev_mode())
            else:
                logger.trace(f"地图 {map_id} 去重后无独有Banks数据，跳过写入")

        # 处理Events数据，只有在启用事件处理时才提取
        if self.process_events and needs_update(
            events_file_base,
            self.version,
            self.force_update,
            dev_mode=self._is_dev_mode(),
        ):
            map_events, dedup_summary = self._extract_map_events(
                bin_file,
                common_event_sources if map_id != "0" else None,
            )
            if dedup_summary:
                self._record_map_event_dedup_summary(map_id, map_data, dedup_summary)
            if map_events:
                final_event_data = self.bin_source._create_base_data(
                    map_id, "map", name=self._get_map_name(map_data), map=map_events
                )
                write_data(final_event_data, events_file_base, dev_mode=self._is_dev_mode())

    def _extract_map_events(
        self,
        bin_file,
        common_event_sources: CommonEventSourceIndex | None = None,
    ) -> tuple[dict | None, dict[str, Any] | None]:
        """
        从BIN文件中提取并根据公共事件集合进行去重

        :param bin_file: BIN文件对象
        :param common_event_sources: 公共事件来源索引，用于去重和记录来源
        :returns: 地图事件数据字典，以及公共事件去重摘要
        """
        map_events = {}
        dedup_by_category: dict[str, dict[str, set[str]]] = {}
        if bin_file.theme_music:
            map_events["theme_music"] = bin_file.theme_music

        all_events_by_category = {}
        for group in bin_file.data:
            if group.music:
                map_events["music"] = group.music.to_dict()
            for event_data in group.bank_units:
                if not event_data.events:
                    continue

                category = event_data.category
                event_strings = [e.string for e in event_data.events]
                unique_events_in_group = list(dict.fromkeys(event_strings))  # 保持顺序的去重

                removed_events: list[str] = []
                if common_event_sources:
                    filtered_events: list[str] = []
                    for event_name in unique_events_in_group:
                        if event_name in common_event_sources:
                            removed_events.append(event_name)
                        else:
                            filtered_events.append(event_name)
                    unique_events_in_group = filtered_events

                if removed_events:
                    category_entry = dedup_by_category.setdefault(category, {"events": set(), "sources": set()})
                    category_entry["events"].update(removed_events)
                    for event_name in removed_events:
                        category_entry["sources"].update(common_event_sources.get(event_name, set()))

                if unique_events_in_group:
                    if category not in all_events_by_category:
                        all_events_by_category[category] = []
                    all_events_by_category[category].extend(unique_events_in_group)

        dedup_summary = None
        if dedup_by_category:
            categories = {}
            total_removed = 0
            for category, payload in dedup_by_category.items():
                removed_event_names = sorted(payload["events"])
                total_removed += len(removed_event_names)
                categories[category] = {
                    "count": len(removed_event_names),
                    "examples": removed_event_names[:5],
                    "sources": sorted(payload["sources"]),
                }
            dedup_summary = {
                "total_removed": total_removed,
                "remaining_event_count": sum(len(events) for events in all_events_by_category.values()),
                "categories": categories,
            }

        if all_events_by_category:
            map_events["events"] = all_events_by_category

        return map_events if map_events else None, dedup_summary

    def _deduplicate_single_map_banks(self, map_data: dict, common_banks_set: set) -> None:
        """
        对单个地图的Banks进行去重处理，移除与公共地图(ID 0)重复的bank path

        :param map_data: 单个地图的完整数据（包含metadata和banks）
        :param common_banks_set: 公共地图的bank path集合（元组形式）
        """
        if "banks" not in map_data:
            return

        bank_paths = map_data["banks"]
        map_id = map_data.get("mapId", "unknown")

        # 记录去重前的统计信息
        original_categories = len(bank_paths)
        original_paths_count = sum(len(paths_list) for paths_list in bank_paths.values())

        # 遍历每个category，移除与公共数据重复的bank path
        categories_to_remove = []
        for category, paths_list in bank_paths.items():
            # 筛选出当前地图独有的、非公共的bank path
            unique_to_map = [path for path in paths_list if tuple(sorted(path)) not in common_banks_set]

            if unique_to_map:
                bank_paths[category] = unique_to_map
            else:
                # 如果该category下所有数据都是公共的，标记为待移除
                categories_to_remove.append(category)

        # 移除完全重复的categories
        for category in categories_to_remove:
            del bank_paths[category]

        # 记录去重后的统计信息
        remaining_categories = len(bank_paths)
        remaining_paths_count = sum(len(paths_list) for paths_list in bank_paths.values())

        logger.trace(
            f"地图 {map_id} Banks去重完成: "
            f"分类 {original_categories}→{remaining_categories}, "
            f"路径 {original_paths_count}→{remaining_paths_count}"
        )

    def _process_map_events_for_id(
        self, map_id: str, map_data: dict, common_event_sources: CommonEventSourceIndex | None = None
    ) -> dict | None:
        """
        提取、去重并保存单个地图的事件数据（兼容性方法）

        :param map_id: 地图ID
        :param map_data: 地图数据字典
        :param common_event_sources: 公共事件来源索引，用于去重
        :returns: 地图事件数据字典，失败时返回None
        """
        # 如果未启用事件处理，直接返回None
        if not self.process_events:
            return None

        if not map_data.get("binPath"):
            return None

        bin_file = self.bin_source._load_map_bin_file(map_id, map_data)
        if bin_file is None:
            return None

        return self._extract_map_events(bin_file, common_event_sources)[0]

    def _record_map_event_dedup_summary(self, map_id: str, map_data: dict, dedup_summary: dict[str, Any]) -> None:
        """记录地图公共事件去重造成的可解释差异。"""
        total_removed = int(dedup_summary.get("total_removed", 0))
        if total_removed <= 0:
            return

        map_name = self._get_map_name(map_data)
        remaining_event_count = int(dedup_summary.get("remaining_event_count", 0))
        source_labels = sorted(
            {
                source.split("/", 1)[0]
                for payload in dedup_summary.get("categories", {}).values()
                for source in payload.get("sources", [])
            }
        )
        source_text = "、".join(source_labels) if source_labels else "公共地图"

        if remaining_event_count == 0:
            message = (
                f"地图 {map_id} ({map_name}) 的事件在与 {source_text} 的公共事件去重后为空，"
                f"共省略 {total_removed} 个事件；单独处理该地图时结果可能不同。"
            )
        else:
            message = (
                f"地图 {map_id} ({map_name}) 有 {total_removed} 个事件因与 {source_text} 的公共事件去重被省略，"
                f"当前仍保留 {remaining_event_count} 个事件。"
            )

        detail_lines = []
        for category, payload in sorted(dedup_summary.get("categories", {}).items()):
            examples = ", ".join(payload.get("examples", [])) or "-"
            sources = ", ".join(payload.get("sources", [])) or "-"
            detail_lines.append(
                f"category={category}, removed={payload.get('count', 0)}, sources=[{sources}], examples=[{examples}]"
            )

        detail = "\n".join(detail_lines)
        record_runtime_note(self.ctx.runtime_cache, "update", message, label="数据更新", detail=detail)
        for line in detail_lines:
            logger.trace(f"地图 {map_id} 公共事件去重明细: {line}")

    def _process_map_banks_for_id(self, map_id: str, map_data: dict) -> dict | None:
        """
        提取单个地图的Banks数据（用于预处理公共地图数据）

        :param map_id: 地图ID
        :param map_data: 地图数据字典
        :returns: 地图Banks数据字典，失败时返回None
        """
        if not map_data.get("binPath"):
            return None

        bin_file = self.bin_source._load_map_bin_file(map_id, map_data)
        if bin_file is None:
            return None

        # 处理Banks数据
        map_banks = {}
        for group in bin_file.data:
            for event_data in group.bank_units:
                if event_data.bank_path:
                    category = event_data.category
                    if category not in map_banks:
                        map_banks[category] = []
                    map_banks[category].append(event_data.bank_path)

        # 去重处理
        for category, paths in map_banks.items():
            unique_paths_tuples = dict.fromkeys(tuple(sorted(p)) for p in paths)
            map_banks[category] = [list(p) for p in unique_paths_tuples]

        if map_banks:
            return {"banks": map_banks}
        return None

    def _get_map_name(self, map_data: dict) -> str:
        """
        获取地图名称，优先使用当前语言，回退到默认语言

        :param map_data: 地图数据
        :returns: 地图名称
        """
        names = map_data.get("names", {})
        if not names:
            return map_data.get("mapStringId", "")

        # 如果有多语言支持，尝试获取当前语言的名称
        for lang in self.languages:
            if lang in names:
                return names[lang]

        # 回退到默认语言
        return names.get("default", map_data.get("mapStringId", ""))
