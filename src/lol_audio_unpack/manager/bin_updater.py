# 🐍 There should be one-- and preferably only one --obvious way to do it.
# 🐼 任何问题应有一种，且最好只有一种，显而易见的解决方法
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2025/7/30 7:40
# @Update  : 2025/7/30 8:12
# @Detail  : 


# 🐍 Explicit is better than implicit.
# 🐼 明了优于隐晦
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2024/7/30 7:50
# @Detail  : BIN文件更新器

import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from league_tools.formats import BIN, WAD
from loguru import logger

from lol_audio_unpack.manager.utils import (
    ProgressTracker,
    get_game_version,
    needs_update,
    read_data,
    write_data,
)
from lol_audio_unpack.utils.common import dump_json
from lol_audio_unpack.utils.config import config

# 类型别名定义
ChampionData = dict[str, Any]


class BinUpdater:
    """
    负责从BIN文件提取音频数据并更新到数据文件中
    """

    def __init__(self, target: str = "all", force_update: bool = False):
        """
        初始化BIN音频更新器
        """
        self.game_path: Path = config.GAME_PATH
        self.manifest_path: Path = config.MANIFEST_PATH
        if not self.game_path or not self.manifest_path:
            raise ValueError("GAME_PATH 和 MANIFEST_PATH 必须在配置中设置")

        self.target = target
        self.force_update = force_update
        self.version: str = get_game_version(self.game_path)
        self.version_manifest_path: Path = self.manifest_path / self.version
        self.data_file_base: Path = self.version_manifest_path / "data"
        self.skin_bank_paths_base: Path = self.version_manifest_path / "skins-bank-paths"
        self.map_bank_paths_base: Path = self.version_manifest_path / "maps-bank-paths"
        self.skin_events_dir: Path = self.version_manifest_path / "events" / "skins"
        self.map_events_dir: Path = self.version_manifest_path / "events" / "maps"

    def update(self) -> None:
        """处理BIN文件，提取皮肤和地图的音频路径和事件数据"""
        data = read_data(self.data_file_base)
        if not data:
            logger.error(f"数据文件不存在，请先运行DataUpdater: {self.data_file_base}")
            raise FileNotFoundError(f"数据文件不存在: {self.data_file_base}")

        try:
            if self.target in ["skin", "all"]:
                self._update_skins(data)
            if self.target in ["map", "all"]:
                self._update_maps(data)
            logger.success(f"BinUpdater 更新完成 (目标: {self.target})")
        except Exception as e:
            logger.error(f"处理BIN文件时出错: {str(e)}")
            if config.is_dev_mode():
                raise

    def _update_skins(self, data: dict) -> None:
        """处理皮肤数据"""
        if not needs_update(self.skin_bank_paths_base, self.version, self.force_update):
            logger.info("皮肤Bank Paths数据已是最新，跳过处理。")
            return

        logger.info("开始处理皮肤音频数据...")
        self.skin_bank_paths_data = {
            "gameVersion": self.version,
            "languages": data.get("languages", []),
            "lastUpdate": datetime.now().isoformat(),
            "skinToChampion": {},
            "championBaseSkins": {},
            "skinAudioMappings": {},
            "skins": {},
        }
        self.skin_events_dir.mkdir(parents=True, exist_ok=True)

        bank_path_to_owner_map: dict[tuple, str] = {}
        champions = data.get("champions", {})
        progress = ProgressTracker(len(champions), "英雄皮肤音频数据处理", log_interval=5)
        sorted_champion_ids = sorted(champions.keys(), key=int)
        for champion_id in sorted_champion_ids:
            champion_data = champions[champion_id]
            self._process_champion_skins(champion_data, champion_id, bank_path_to_owner_map)
            progress.update()
        progress.finish()
        self._optimize_mappings()

        write_data(self.skin_bank_paths_data, self.skin_bank_paths_base)
        logger.success("皮肤Bank Paths数据更新完成")

    def _update_maps(self, data: dict) -> None:
        """处理地图数据"""
        if not needs_update(self.map_bank_paths_base, self.version, self.force_update):
            logger.info("地图Bank Paths数据已是最新，跳过处理。")
            return

        logger.info("开始处理地图音频数据...")
        self.map_bank_paths_data = {
            "gameVersion": self.version,
            "languages": data.get("languages", []),
            "lastUpdate": datetime.now().isoformat(),
            "maps": {},
        }
        self.map_events_dir.mkdir(parents=True, exist_ok=True)
        maps = data.get("maps", {})

        common_events_set = set()
        if "0" in maps:
            logger.debug("正在预处理公共地图(ID 0)的事件数据...")
            try:
                if map_events := self._process_map_events_for_id("0", maps["0"]):
                    if "events" in map_events:
                        for events_list in map_events["events"].values():
                            for event in events_list:
                                common_events_set.add(frozenset(event.items()))
            except Exception as e:
                logger.error(f"预处理公共地图(ID 0)的事件时出错: {e}")
                if config.is_dev_mode():
                    raise

        map_progress = ProgressTracker(len(maps), "地图音频与事件数据处理", log_interval=1)
        for map_id, map_data in maps.items():
            self._process_map_bank_paths(map_id, map_data)
            if map_id != "0":
                try:
                    self._process_map_events_for_id(map_id, map_data, common_events_set)
                except Exception as e:
                    logger.error(f"处理地图 {map_id} 的事件时出错: {e}")
                    if config.is_dev_mode():
                        raise
            map_progress.update()
        map_progress.finish()

        self._deduplicate_map_bank_paths()

        write_data(self.map_bank_paths_data, self.map_bank_paths_base)
        logger.success("地图Bank Paths数据更新完成")

    def _process_champion_skins(
        self, champion_data: ChampionData, champion_id: str, bank_path_to_owner_map: dict
    ) -> None:
        """处理单个英雄的所有皮肤，提取音频数据并建立映射关系"""
        alias = champion_data.get("alias", "").lower()
        if not alias:
            return

        path_to_skin_id_map: dict[str, str] = {}
        skins_data = champion_data.get("skins", [])
        sorted_skins_data = sorted(skins_data, key=lambda s: int(s["id"]))

        base_skin_id = None
        for skin in sorted_skins_data:
            skin_id_str = str(skin["id"])
            self.skin_bank_paths_data["skinToChampion"][skin_id_str] = champion_id
            if skin.get("isBase"):
                base_skin_id = skin_id_str
                self.skin_bank_paths_data["championBaseSkins"][champion_id] = base_skin_id

            if bin_path := skin.get("binPath"):
                path_to_skin_id_map[bin_path] = skin_id_str
            for chroma in skin.get("chromas", []):
                chroma_id_str = str(chroma["id"])
                self.skin_bank_paths_data["skinToChampion"][chroma_id_str] = champion_id
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
            logger.debug(f"从 {alias} 提取 {len(bin_paths)} 个BIN文件")
            bin_raws = WAD(full_wad_path).extract(bin_paths, raw=True)
            raw_data_map = dict(zip(bin_paths, bin_raws, strict=False))
        except Exception as e:
            logger.error(f"处理英雄 {alias} 的WAD文件时出错: {e}")
            logger.debug(traceback.format_exc())
            return

        skin_ids_sorted = sorted(path_to_skin_id_map.values(), key=int)
        path_to_id_reversed = {v: k for k, v in path_to_skin_id_map.items()}

        champion_skin_events = {}
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
                                    if skin_id not in self.skin_bank_paths_data["skinAudioMappings"]:
                                        self.skin_bank_paths_data["skinAudioMappings"][skin_id] = {}
                                    self.skin_bank_paths_data["skinAudioMappings"][skin_id][category] = owner_id
                            else:
                                bank_path_to_owner_map[bank_path_fingerprint] = skin_id
                                if skin_id not in self.skin_bank_paths_data["skins"]:
                                    self.skin_bank_paths_data["skins"][skin_id] = {}
                                if category not in self.skin_bank_paths_data["skins"][skin_id]:
                                    self.skin_bank_paths_data["skins"][skin_id][category] = []
                                self.skin_bank_paths_data["skins"][skin_id][category].append(event_data.bank_path)

                                if is_new_skin_entry:
                                    if skin_events := self._extract_skin_events(bin_file, base_skin_id, skin_id):
                                        champion_skin_events[skin_id] = skin_events
                                    is_new_skin_entry = False

            except Exception as e:
                logger.error(f"解析皮肤BIN失败: {path}, 错误: {e}")
                if config.is_dev_mode():
                    raise

        if champion_skin_events:
            event_file_base = self.skin_events_dir / f"{champion_id}"
            if needs_update(event_file_base, self.version, self.force_update):
                final_event_data = {
                    "gameVersion": self.version,
                    "languages": self.skin_bank_paths_data.get("languages", []),
                    "lastUpdate": datetime.now().isoformat(),
                    "skins": champion_skin_events,
                }
                write_data(final_event_data, event_file_base)

    def _extract_skin_events(self, bin_file: BIN, base_skin_id: str | None, current_skin_id: str) -> dict | None:
        """提取一个皮肤BIN文件中的所有事件数据"""
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
                    all_events_by_category[category].extend([e.to_dict() for e in event_data.events])

        if all_events_by_category:
            skin_events["events"] = all_events_by_category

        return skin_events if skin_events else None

    def _process_map_bank_paths(self, map_id: str, map_data: dict) -> None:
        """处理单个地图的Bank Paths"""
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
        except Exception as e:
            logger.error(f"提取或解析地图 {map_id} 的BIN文件时出错: {e}")
            if config.is_dev_mode():
                raise
            return

        map_bank_paths = {}
        for group in bin_file.data:
            for event_data in group.bank_units:
                if event_data.bank_path:
                    category = event_data.category
                    if category not in map_bank_paths:
                        map_bank_paths[category] = []
                    map_bank_paths[category].append(event_data.bank_path)

        for category, paths in map_bank_paths.items():
            unique_paths_tuples = dict.fromkeys(tuple(sorted(p)) for p in paths)
            map_bank_paths[category] = [list(p) for p in unique_paths_tuples]

        if map_bank_paths:
            self.map_bank_paths_data["maps"][map_id] = map_bank_paths

    def _process_map_events_for_id(
        self, map_id: str, map_data: dict, common_events_set: set | None = None
    ) -> dict | None:
        """提取、去重并保存单个地图的事件数据"""
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

        if map_events := self._extract_map_events(bin_file, common_events_set):
            event_file_base = self.map_events_dir / f"{map_id}"
            if needs_update(event_file_base, self.version, self.force_update):
                final_event_data = {
                    "gameVersion": self.version,
                    "languages": self.map_bank_paths_data.get("languages", []),
                    "lastUpdate": datetime.now().isoformat(),
                    "map": map_events,
                }
                write_data(final_event_data, event_file_base)
            return map_events
        return None

    def _extract_map_events(self, bin_file: BIN, common_events_set: set | None = None) -> dict | None:
        """从BIN文件中提取并根据公共事件集合进行去重"""
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

                events_as_dicts = [e.to_dict() for e in event_data.events]
                unique_events_in_group = list({frozenset(event.items()): event for event in events_as_dicts}.values())

                if common_events_set:
                    unique_events_in_group = [
                        e for e in unique_events_in_group if frozenset(e.items()) not in common_events_set
                    ]

                if unique_events_in_group:
                    category = event_data.category
                    if category not in all_events_by_category:
                        all_events_by_category[category] = []
                    all_events_by_category[category].extend(unique_events_in_group)

        if all_events_by_category:
            map_events["events"] = all_events_by_category

        return map_events if map_events else None

    def _deduplicate_map_bank_paths(self) -> None:
        """基于ID为0的地图数据，对其他地图的Bank Paths进行去重"""
        logger.info("开始对地图bank path数据进行全局去重...")
        common_bank_paths = self.map_bank_paths_data["maps"].get("0", {})
        if not common_bank_paths:
            logger.warning("未找到ID为0的公共地图bank path数据，跳过 bank path 去重。")
            return

        common_paths_set = set()
        for paths_list in common_bank_paths.values():
            for path in paths_list:
                common_paths_set.add(tuple(sorted(path)))

        for map_id, categories in self.map_bank_paths_data["maps"].copy().items():
            if map_id == "0":
                continue

            for category, paths_list in categories.copy().items():
                unique_to_map = [path for path in paths_list if tuple(sorted(path)) not in common_paths_set]

                if unique_to_map:
                    categories[category] = unique_to_map
                else:
                    del categories[category]

            if not categories:
                del self.map_bank_paths_data["maps"][map_id]
        logger.success("地图bank path数据去重完成。")

    def _optimize_mappings(self) -> None:
        """优化映射关系，将部分共享升级为完全共享"""
        for skin_id, mappings in self.skin_bank_paths_data["skinAudioMappings"].copy().items():
            if not isinstance(mappings, dict):
                continue

            owner_ids = set(mappings.values())
            if len(owner_ids) == 1:
                owner_id = owner_ids.pop()
                if skin_id not in self.skin_bank_paths_data["skins"]:
                    self.skin_bank_paths_data["skinAudioMappings"][skin_id] = owner_id
