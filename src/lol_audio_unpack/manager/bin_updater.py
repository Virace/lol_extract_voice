# 🐍 There should be one-- and preferably only one --obvious way to do it.
# 🐼 任何问题应有一种，且最好只有一种，显而易见的解决方法
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2025/7/30 7:40
# @Update  : 2025/8/3 8:57
# @Detail  : BIN文件更新器


from datetime import datetime
from pathlib import Path
from typing import Any

from alive_progress import alive_it
from league_tools.formats import BIN, WAD
from loguru import logger

from lol_audio_unpack.manager.utils import (
    create_metadata_object,
    get_game_version,
    needs_update,
    read_data,
    write_data,
)
from lol_audio_unpack.utils.config import config
from lol_audio_unpack.utils.logging import performance_monitor

# 类型别名定义
ChampionData = dict[str, Any]


class BinUpdater:
    """
    负责从BIN文件提取音频数据并更新到数据文件中

    支持可选的事件处理：设置 process_events=False 可显著提升处理速度，但不会生成事件数据
    """

    def __init__(self, force_update: bool = False, process_events: bool = True):
        """
        初始化BIN音频更新器

        :param force_update: 是否强制更新，忽略版本检查
        :param process_events: 是否处理事件数据（默认True，设置为False可大幅提升处理速度）
        """
        self.game_path: Path = config.GAME_PATH
        self.manifest_path: Path = config.MANIFEST_PATH
        if not self.game_path or not self.manifest_path:
            raise ValueError("GAME_PATH 和 MANIFEST_PATH 必须在配置中设置")

        self.force_update = force_update
        self.process_events = process_events
        self.version: str = get_game_version(self.game_path)
        self.version_manifest_path: Path = self.manifest_path / self.version
        self.data_file_base: Path = self.version_manifest_path / "data"
        self.champion_banks_dir: Path = self.version_manifest_path / "banks" / "champions"
        self.map_banks_dir: Path = self.version_manifest_path / "banks" / "maps"
        self.champion_events_dir: Path = self.version_manifest_path / "events" / "champions"
        self.map_events_dir: Path = self.version_manifest_path / "events" / "maps"
        self.languages: list[str] = []  # 在update()中初始化

    @logger.catch
    @performance_monitor(level="INFO")
    def update(
        self,
        target: str = "all",
        champion_ids: list[str] | None = None,
        map_ids: list[str] | None = None,
    ) -> None:
        """
        处理BIN文件，提取皮肤和地图的音频路径和事件数据

        :param target: 处理目标，可选值：'all', 'skin', 'map'。当指定具体IDs时该参数被忽略
        :param champion_ids: 指定要处理的英雄ID列表，为None时处理所有英雄
        :param map_ids: 指定要处理的地图ID列表，为None时处理所有地图
        """
        data = read_data(self.data_file_base)
        if not data:
            logger.error(f"数据文件不存在，请先运行DataUpdater: {self.data_file_base}")
            raise FileNotFoundError(f"数据文件不存在: {self.data_file_base}")

        self.languages = data.get("metadata", {}).get("languages", [])

        # 根据传入的IDs构建筛选后的数据
        if champion_ids or map_ids:
            # 精确模式：根据具体ID筛选数据
            filtered_data = self._filter_data_by_ids(data, champion_ids, map_ids)
            if champion_ids and filtered_data.get("champions"):
                self._update_champions(filtered_data)
            if map_ids and filtered_data.get("maps"):
                self._update_maps(filtered_data)
            logger.success(f"BinUpdater 更新完成 (精确模式: champions={champion_ids}, maps={map_ids})")
        else:
            # 批量模式：使用target控制
            if target in ["skin", "all"]:
                self._update_champions(data)
            if target in ["map", "all"]:
                self._update_maps(data)
            logger.success(f"BinUpdater 更新完成 (批量模式: {target})")

    def _filter_data_by_ids(self, data: dict, champion_ids: list[str] | None, map_ids: list[str] | None) -> dict:
        """
        根据指定的ID列表筛选数据

        :param data: 完整的数据字典
        :param champion_ids: 要筛选的英雄ID列表
        :param map_ids: 要筛选的地图ID列表
        :returns: 筛选后的数据字典，保持原有结构
        """
        filtered_data = {
            "languages": data.get("languages", []),
            # 其他基础字段保持不变
        }

        # 筛选英雄数据
        if champion_ids:
            all_champions = data.get("champions", {})
            filtered_champions = {}
            for champion_id in champion_ids:
                if champion_id in all_champions:
                    filtered_champions[champion_id] = all_champions[champion_id]
                else:
                    logger.warning(f"指定的英雄ID {champion_id} 在数据中不存在")
            if filtered_champions:
                filtered_data["champions"] = filtered_champions

        # 筛选地图数据
        if map_ids:
            all_maps = data.get("maps", {})
            filtered_maps = {}
            for map_id in map_ids:
                if map_id in all_maps:
                    filtered_maps[map_id] = all_maps[map_id]
                else:
                    logger.warning(f"指定的地图ID {map_id} 在数据中不存在")
            if filtered_maps:
                filtered_data["maps"] = filtered_maps

        return filtered_data

    @performance_monitor(level="DEBUG")
    def _update_champions(self, data: dict) -> None:
        """
        处理英雄数据，按英雄ID分别生成文件

        :param data: 包含英雄数据的字典
        """
        logger.info("开始处理英雄音频数据...")
        self.champion_banks_dir.mkdir(parents=True, exist_ok=True)
        self.champion_events_dir.mkdir(parents=True, exist_ok=True)

        champions = data.get("champions", {})
        sorted_champion_ids = sorted(champions.keys(), key=int)

        champion_bar = alive_it(sorted_champion_ids, title="英雄音频数据处理")
        for champion_id in champion_bar:
            champion_data = champions[champion_id]
            champion_bar.text(f"处理英雄 {champion_id}")
            self._process_champion_skins(champion_data, champion_id)

        logger.success("英雄Banks数据更新完成")

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
        common_events_set = set()
        common_banks_set = set()
        if "0" in maps:
            logger.debug("正在预处理公共地图(ID 0)的数据...")
            try:
                # 预处理事件数据
                if map_events := self._process_map_events_for_id("0", maps["0"]):
                    if "events" in map_events:
                        for events_list in map_events["events"].values():
                            for event_string in events_list:
                                common_events_set.add(event_string)

                # 预处理Banks数据
                if map_banks := self._process_map_banks_for_id("0", maps["0"]):
                    if "banks" in map_banks:
                        for paths_list in map_banks["banks"].values():
                            for path in paths_list:
                                common_banks_set.add(tuple(sorted(path)))
            except Exception:
                logger.opt(exception=True).error("预处理公共地图(ID 0)的数据时出错")
                if config.is_dev_mode():
                    raise

        map_bar = alive_it(maps.items(), title="地图音频与事件数据处理")
        for map_id, map_data in map_bar:
            map_bar.text(f"处理地图 {map_id}")
            self._process_single_map(map_id, map_data, common_events_set, common_banks_set)

        logger.success("地图Banks数据更新完成")

    @performance_monitor(level="DEBUG")
    def _process_champion_skins(self, champion_data: ChampionData, champion_id: str) -> None:
        """
        处理单个英雄的所有皮肤，提取音频数据并生成独立文件

        :param champion_data: 英雄数据字典
        :param champion_id: 英雄ID
        """
        alias = champion_data.get("alias", "").lower()
        if not alias:
            return

        # 检查是否需要更新
        banks_file_base = self.champion_banks_dir / champion_id
        events_file_base = self.champion_events_dir / champion_id

        if not needs_update(banks_file_base, self.version, self.force_update) and not needs_update(
            events_file_base, self.version, self.force_update
        ):
            logger.trace(f"英雄 {champion_id} ({alias}) 的数据已是最新，跳过处理")
            return

        path_to_skin_id_map: dict[str, str] = {}
        skins_data = champion_data.get("skins", [])
        sorted_skins_data = sorted(skins_data, key=lambda s: int(s["id"]))

        base_skin_id = None
        for skin in sorted_skins_data:
            skin_id_str = str(skin["id"])
            if skin.get("isBase"):
                base_skin_id = skin_id_str

            if bin_path := skin.get("binPath"):
                path_to_skin_id_map[bin_path] = skin_id_str
            for chroma in skin.get("chromas", []):
                chroma_id_str = str(chroma["id"])
                if bin_path := chroma.get("binPath"):
                    path_to_skin_id_map[bin_path] = chroma_id_str

        if not path_to_skin_id_map:
            return

        root_wad_path = champion_data["wad"].get("root")
        if not root_wad_path:
            return

        full_wad_path = self.game_path / root_wad_path
        if not full_wad_path.exists():
            logger.warning(f"英雄 {alias} 的WAD文件不存在: {full_wad_path}")
            return

        bin_paths = list(path_to_skin_id_map.keys())
        try:
            logger.trace(f"从 {alias} 提取 {len(bin_paths)} 个BIN文件")
            bin_raws = WAD(full_wad_path).extract(bin_paths, raw=True)
            raw_data_map = dict(zip(bin_paths, bin_raws, strict=False))
        except Exception:
            logger.opt(exception=True).error(f"处理英雄 {alias} 的WAD文件时出错")
            return

        skin_ids_sorted = sorted(path_to_skin_id_map.values(), key=int)
        path_to_id_reversed = {v: k for k, v in path_to_skin_id_map.items()}

        # 初始化英雄的banks和events数据
        champion_banks_data = self._create_base_data(
            champion_id, "champion", alias=alias, skinAudioMappings={}, skins={}
        )

        champion_skin_events = {}
        bank_path_to_owner_map: dict[tuple, str] = {}

        for skin_id in skin_ids_sorted:
            path = path_to_id_reversed[skin_id]
            if not (bin_raw := raw_data_map.get(path)):
                continue

            try:
                bin_file = BIN(bin_raw)
                is_new_skin_entry = True

                for group in bin_file.data:
                    for event_data in group.bank_units:
                        if event_data.bank_path:
                            bank_path_fingerprint = tuple(sorted(event_data.bank_path))
                            category = event_data.category

                            if owner_id := bank_path_to_owner_map.get(bank_path_fingerprint):
                                if skin_id != owner_id and "_Base_" not in category:
                                    if skin_id not in champion_banks_data["skinAudioMappings"]:
                                        champion_banks_data["skinAudioMappings"][skin_id] = {}
                                    champion_banks_data["skinAudioMappings"][skin_id][category] = owner_id
                            else:
                                bank_path_to_owner_map[bank_path_fingerprint] = skin_id
                                if skin_id not in champion_banks_data["skins"]:
                                    champion_banks_data["skins"][skin_id] = {}
                                if category not in champion_banks_data["skins"][skin_id]:
                                    champion_banks_data["skins"][skin_id][category] = []
                                champion_banks_data["skins"][skin_id][category].append(event_data.bank_path)

                                if is_new_skin_entry and self.process_events:
                                    if skin_events := self._extract_skin_events(bin_file, base_skin_id, skin_id):
                                        champion_skin_events[skin_id] = skin_events
                                    is_new_skin_entry = False

            except Exception:
                logger.opt(exception=True).error(f"解析皮肤BIN失败: {path}")
                if config.is_dev_mode():
                    raise

        # 优化映射关系
        self._optimize_champion_mappings(champion_banks_data)

        # 写入banks数据
        if needs_update(banks_file_base, self.version, self.force_update):
            write_data(champion_banks_data, banks_file_base)

        # 写入events数据
        if champion_skin_events and needs_update(events_file_base, self.version, self.force_update):
            final_event_data = self._create_base_data(champion_id, "champion", alias=alias, skins=champion_skin_events)
            write_data(final_event_data, events_file_base)

    def _process_single_map(
        self, map_id: str, map_data: dict, common_events_set: set | None = None, common_banks_set: set | None = None
    ) -> None:
        """
        处理单个地图的Banks和Events数据

        :param map_id: 地图ID
        :param map_data: 地图数据字典
        :param common_events_set: 公共事件集合，用于去重
        :param common_banks_set: 公共Banks集合，用于去重
        """
        banks_file_base = self.map_banks_dir / map_id
        events_file_base = self.map_events_dir / map_id

        if not needs_update(banks_file_base, self.version, self.force_update) and not needs_update(
            events_file_base, self.version, self.force_update
        ):
            logger.trace(f"地图 {map_id} 的数据已是最新，跳过处理")
            return

        if not map_data.get("wad") or not map_data.get("binPath"):
            return

        wad_path = self.game_path / map_data["wad"]["root"]
        bin_path = map_data["binPath"]

        if not wad_path.exists():
            return

        try:
            bin_raws = WAD(wad_path).extract([bin_path], raw=True)
            if not bin_raws or not bin_raws[0]:
                return
            bin_file = BIN(bin_raws[0])
        except Exception:
            logger.opt(exception=True).error(f"提取或解析地图 {map_id} 的BIN文件时出错")
            if config.is_dev_mode():
                raise
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
        if map_banks and needs_update(banks_file_base, self.version, self.force_update):
            map_banks_data = self._create_base_data(map_id, "map", name=self._get_map_name(map_data), banks=map_banks)

            # 对非公共地图进行去重处理
            if map_id != "0" and common_banks_set:
                self._deduplicate_single_map_banks(map_banks_data, common_banks_set)

            # 去重后检查是否还有数据需要写入
            if map_banks_data.get("banks"):
                write_data(map_banks_data, banks_file_base)
            else:
                logger.trace(f"地图 {map_id} 去重后无独有Banks数据，跳过写入")

        # 处理Events数据，只有在启用事件处理时才提取
        if self.process_events and needs_update(events_file_base, self.version, self.force_update):
            if map_events := self._extract_map_events(bin_file, common_events_set if map_id != "0" else None):
                final_event_data = self._create_base_data(
                    map_id, "map", name=self._get_map_name(map_data), map=map_events
                )
                write_data(final_event_data, events_file_base)

    def _extract_skin_events(self, bin_file: BIN, base_skin_id: str | None, current_skin_id: str) -> dict | None:
        """
        提取一个皮肤BIN文件中的所有事件数据

        :param bin_file: BIN文件对象
        :param base_skin_id: 基础皮肤ID，用于过滤基础皮肤事件
        :param current_skin_id: 当前皮肤ID
        :returns: 皮肤事件数据字典，无数据时返回None
        """
        skin_events = {}
        if bin_file.theme_music:
            skin_events["theme_music"] = bin_file.theme_music

        all_events_by_category = {}
        for group in bin_file.data:
            if group.music:
                skin_events["music"] = group.music.to_dict()
            for event_data in group.bank_units:
                if base_skin_id and current_skin_id != base_skin_id and "_Base_" in event_data.category:
                    continue
                if event_data.events:
                    category = event_data.category
                    if category not in all_events_by_category:
                        all_events_by_category[category] = []
                    event_strings = [e.string for e in event_data.events]
                    # 添加到category，稍后统一去重
                    all_events_by_category[category].extend(event_strings)

        if all_events_by_category:
            # 对每个category的事件列表进行去重
            for category, events_list in all_events_by_category.items():
                all_events_by_category[category] = list(dict.fromkeys(events_list))  # 保持顺序的去重
            skin_events["events"] = all_events_by_category

        return skin_events if skin_events else None

    def _extract_map_events(self, bin_file: BIN, common_events_set: set | None = None) -> dict | None:
        """
        从BIN文件中提取并根据公共事件集合进行去重

        :param bin_file: BIN文件对象
        :param common_events_set: 公共事件集合，用于去重
        :returns: 地图事件数据字典，无数据时返回None
        """
        map_events = {}
        if bin_file.theme_music:
            map_events["theme_music"] = bin_file.theme_music

        all_events_by_category = {}
        for group in bin_file.data:
            if group.music:
                map_events["music"] = group.music.to_dict()
            for event_data in group.bank_units:
                if not event_data.events:
                    continue

                event_strings = [e.string for e in event_data.events]
                unique_events_in_group = list(dict.fromkeys(event_strings))  # 保持顺序的去重

                if common_events_set:
                    unique_events_in_group = [e for e in unique_events_in_group if e not in common_events_set]

                if unique_events_in_group:
                    category = event_data.category
                    if category not in all_events_by_category:
                        all_events_by_category[category] = []
                    all_events_by_category[category].extend(unique_events_in_group)

        if all_events_by_category:
            map_events["events"] = all_events_by_category

        return map_events if map_events else None

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

    def _optimize_champion_mappings(self, champion_data: dict) -> None:
        """
        优化单个英雄的映射关系，将部分共享升级为完全共享

        :param champion_data: 英雄数据字典
        """
        for skin_id, mappings in champion_data["skinAudioMappings"].copy().items():
            if not isinstance(mappings, dict):
                continue

            owner_ids = set(mappings.values())
            if len(owner_ids) == 1:
                owner_id = owner_ids.pop()
                if skin_id not in champion_data["skins"]:
                    champion_data["skinAudioMappings"][skin_id] = owner_id

    def _process_map_events_for_id(
        self, map_id: str, map_data: dict, common_events_set: set | None = None
    ) -> dict | None:
        """
        提取、去重并保存单个地图的事件数据（兼容性方法）

        :param map_id: 地图ID
        :param map_data: 地图数据字典
        :param common_events_set: 公共事件集合，用于去重
        :returns: 地图事件数据字典，失败时返回None
        """
        # 如果未启用事件处理，直接返回None
        if not self.process_events:
            return None

        if not map_data.get("wad") or not map_data.get("binPath"):
            return None

        wad_path = self.game_path / map_data["wad"]["root"]
        bin_path = map_data["binPath"]

        if not wad_path.exists():
            return None

        try:
            bin_raws = WAD(wad_path).extract([bin_path], raw=True)
            if not bin_raws or not bin_raws[0]:
                return None
            bin_file = BIN(bin_raws[0])
        except Exception:
            return None

        return self._extract_map_events(bin_file, common_events_set)

    def _process_map_banks_for_id(self, map_id: str, map_data: dict) -> dict | None:
        """
        提取单个地图的Banks数据（用于预处理公共地图数据）

        :param map_id: 地图ID
        :param map_data: 地图数据字典
        :returns: 地图Banks数据字典，失败时返回None
        """
        if not map_data.get("wad") or not map_data.get("binPath"):
            return None

        wad_path = self.game_path / map_data["wad"]["root"]
        bin_path = map_data["binPath"]

        if not wad_path.exists():
            return None

        try:
            bin_raws = WAD(wad_path).extract([bin_path], raw=True)
            if not bin_raws or not bin_raws[0]:
                return None
            bin_file = BIN(bin_raws[0])
        except Exception:
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

    def _create_base_data(self, entity_id: str, entity_type: str, **extra_fields) -> dict:
        """
        创建包含元数据和实体特定信息的基础数据结构。

        :param entity_id: 实体ID（英雄ID或地图ID）
        :param entity_type: 实体类型（'champion' 或 'map'）
        :param extra_fields: 任何要添加到顶层的额外字段
        :return: 包含元数据和附加字段的基础字典
        """
        # 使用通用函数创建包含所有标准元数据的对象
        base_data = create_metadata_object(self.version, self.languages)

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
