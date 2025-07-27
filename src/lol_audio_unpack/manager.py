# 🐍 Explicit is better than implicit.
# 🐼 明了优于隐晦
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2024/5/6 1:19
# @Update  : 2025/7/28 4:24
# @Detail  : 游戏数据管理器


import json
import re
import shutil
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from league_tools.formats import BIN, WAD
from league_tools.formats.bin.models import EventData
from loguru import logger

from lol_audio_unpack.Utils.common import Singleton, dump_json, format_region, load_json
from lol_audio_unpack.Utils.config import config
from lol_audio_unpack.Utils.type_hints import StrPath

# 类型别名定义
ChampionData = dict[str, Any]
SkinData = dict[str, Any]
AudioData = dict[str, list[str]]
BinMapping = dict[str, dict[str, Any]]


def get_game_version(game_path: Path) -> str:
    """
    获取游戏版本

    :param game_path: 游戏根目录路径
    :return: 游戏版本号
    """
    meta = game_path / "Game" / "content-metadata.json"
    if not meta.exists():
        raise FileNotFoundError("content-metadata.json 文件不存在，无法判断版本信息")

    with open(meta, encoding="utf-8") as f:
        data = json.load(f)

    version_v = data["version"]

    if m := re.match(r"^(\d+\.\d+)\.", version_v):
        return m.group(1)

    raise ValueError(f"无法解析版本号: {version_v}")


class ProgressTracker:
    """
    进度跟踪器，用于记录和显示处理进度
    """

    def __init__(self, total: int, description: str, log_interval: int = 10):
        """
        初始化进度跟踪器

        :param total: 总项目数
        :param description: 进度描述
        :param log_interval: 日志记录间隔
        """
        self.total = total
        self.current = 0
        self.description = description
        self.log_interval = log_interval
        self.start_time = datetime.now()
        logger.info(f"开始{description}，总计 {total} 项")

    def update(self, increment: int = 1) -> None:
        """
        更新进度

        :param increment: 增量，默认为1
        """
        self.current += increment
        if self.current % self.log_interval == 0 or self.current == self.total:
            elapsed = (datetime.now() - self.start_time).total_seconds()
            percentage = (self.current / self.total) * 100
            logger.info(
                f"{self.description}进度: {self.current}/{self.total} ({percentage:.1f}%)，已用时 {elapsed:.1f}秒"
            )

    def finish(self) -> None:
        """
        完成进度跟踪，显示最终结果
        """
        elapsed = (datetime.now() - self.start_time).total_seconds()
        logger.success(f"{self.description}完成，共 {self.current}/{self.total} 项，用时 {elapsed:.1f}秒")


class DataUpdater:
    """
    负责游戏数据的更新和多语言JSON合并
    """

    def __init__(self, languages: list[str] | None = None) -> None:
        """
        初始化数据更新器

        :param languages: 需要处理的语言列表（不包括default，default会自动添加）。
                        如果为None，则使用config中的GAME_REGION。
        """
        # 从配置中获取游戏根目录
        self.game_path: Path = config.GAME_PATH
        # 从配置中获取数据清单输出目录
        self.manifest_path: Path = config.MANIFEST_PATH
        # 临时工作目录，用于存放解包过程中的临时文件
        self.temp_path: Path = config.TEMP_PATH

        if not self.game_path or not self.manifest_path:
            raise ValueError("GAME_PATH 和 MANIFEST_PATH 必须在配置中设置")

        # 处理语言列表
        if languages is None:
            # 从config获取，如果没有则使用默认值
            game_region = config.GAME_REGION or "zh_CN"
            # 需要处理的目标语言列表
            self.languages: list[str] = [game_region]
        else:
            self.languages: list[str] = languages

        # 当前游戏版本，如 "14.14"
        self.version: str = get_game_version(self.game_path)
        # 特定版本的数据清单文件目录
        self.version_manifest_path: Path = self.manifest_path / self.version
        # 最终合并的数据文件路径
        self.data_file: Path = self.version_manifest_path / "data.json"
        # 实际处理的语言列表，包含 "default"
        self.process_languages: list[str] = self._prepare_language_list(self.languages)

        # 确保版本清单目录存在
        self.version_manifest_path.mkdir(parents=True, exist_ok=True)

    def _prepare_language_list(self, languages: list[str]) -> list[str]:
        """
        准备处理语言列表，确保default在列表中

        :param languages: 输入的语言列表
        :return: 处理后的语言列表
        """
        process_languages = ["default"]
        for lang in languages:
            if lang.lower() not in ["default", "en_us"]:
                process_languages.append(lang)
        return process_languages

    @staticmethod
    def _normalize_text(text: str) -> str:
        """
        标准化文本，替换不间断空格等与下游工具不兼容的字符

        :param text: 输入文本
        :return: 标准化后的文本
        """
        if not isinstance(text, str):
            return text
        return text.replace("\u00a0", " ")

    def check_and_update(self) -> Path:
        """
        检查游戏版本并更新数据

        :return: 合并后的数据文件路径
        """
        # 检查是否需要更新
        if not self._needs_update():
            return self.data_file

        # 使用config中的TEMP_PATH创建本次运行的临时目录
        # 通过添加时间戳确保每次运行的目录唯一
        run_temp_path = self.temp_path / f"update_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        run_temp_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"创建临时目录用于解包: {run_temp_path}")

        try:
            # 提取和处理数据
            self._process_data(run_temp_path)
            logger.success(f"数据更新完成: {self.data_file}")
            return self.data_file
        finally:
            # 根据是否为开发模式决定是否删除临时目录
            if not config.is_dev_mode():
                try:
                    shutil.rmtree(run_temp_path)
                    logger.info(f"已清理临时目录: {run_temp_path}")
                except OSError as e:
                    logger.error(f"清理临时目录失败: {run_temp_path}, error: {e}")
            else:
                logger.warning(f"开发模式，临时目录未删除: {run_temp_path}")

    def _needs_update(self) -> bool:
        """
        检查是否需要更新数据

        :return: 是否需要更新
        """
        if not self.data_file.exists():
            return True

        try:
            with open(self.data_file, encoding="utf-8") as f:
                existing_data = json.load(f)

            # 检查现有文件包含的语言
            existing_languages = set(existing_data.get("languages", []))
            existing_languages.add("default")  # default总是包含的

            # 检查请求的所有语言是否都已包含
            requested_languages = set(self.process_languages)

            # 如果所有请求的语言都已包含在现有文件中，则不需要更新
            if requested_languages.issubset(existing_languages):
                logger.info(f"数据文件已是最新版本: {self.version}，且包含所有请求的语言")
                return False
            else:
                missing_langs = requested_languages - existing_languages
                logger.info(f"需要更新数据文件，缺少语言: {missing_langs}")
                return True
        except Exception as e:
            logger.error(f"检查现有数据文件时出错: {str(e)}")
            # 出错时默认需要更新
            if config.is_dev_mode():
                raise
            return True

    def _process_data(self, temp_path: Path) -> None:
        """
        处理游戏数据，包括提取、合并和验证

        :param temp_path: 临时路径
        """
        # 创建进度跟踪器
        progress = ProgressTracker(len(self.process_languages), "语言数据提取", log_interval=1)

        # 提取需要的数据
        for language in self.process_languages:
            logger.info(f"正在处理 {language} 语言数据...")
            self._extract_wad_data(temp_path, language)
            progress.update()
        progress.finish()

        # 合并多语言数据
        logger.info("合并多语言数据...")
        self._merge_and_build_data(temp_path)

        # 将合并后的数据文件复制到输出目录
        temp_data_file = temp_path / self.version / "data.json"
        if temp_data_file.exists():
            self.version_manifest_path.mkdir(parents=True, exist_ok=True)
            shutil.copy2(temp_data_file, self.data_file)
            logger.info(f"已复制合并数据到: {self.data_file}")
        else:
            raise FileNotFoundError(f"未能创建合并数据文件: {temp_data_file}")

    def _load_language_json(self, base_path: Path, filename_template: str) -> dict[str, Any]:
        """
        加载指定模板的、所有语言的JSON文件

        :param base_path: 版本基础路径
        :param filename_template: 文件名模板，用{lang}作为语言占位符
        :return: 一个字典，键是语言代码，值是加载的JSON数据
        """
        loaded_data = {}
        for lang in self.process_languages:
            file_path = base_path / lang / filename_template.format(lang=lang)
            if file_path.exists():
                loaded_data[lang] = load_json(file_path)
            else:
                logger.warning(f"未找到JSON文件: {file_path}")
        return loaded_data

    def _merge_and_build_data(self, temp_dir: Path) -> None:
        """
        聚合所有数据处理和合并逻辑，生成最终的data.json

        :param temp_dir: 包含已提取数据的临时目录
        """
        base_path = temp_dir / self.version
        summaries = self._load_language_json(base_path, "champion-summary.json")

        if "default" not in summaries:
            logger.error("未找到default语言的英雄概要数据，无法继续处理")
            return

        final_champions = {}
        progress = ProgressTracker(len(summaries["default"]), "英雄数据合并", log_interval=10)

        for i, default_summary in enumerate(summaries["default"]):
            champ_id = str(default_summary["id"])
            if champ_id == "-1":
                continue

            alias = self._normalize_text(default_summary["alias"])
            details = self._load_language_json(base_path, f"champions/{champ_id}.json")
            default_details = details.get("default", {})

            # 1. 合并英雄基础信息 (name, title, description)
            names = {lang: self._normalize_text(summ[i]["name"]) for lang, summ in summaries.items() if i < len(summ)}
            titles = {lang: self._normalize_text(det.get("title", "")) for lang, det in details.items()}
            descriptions = {
                lang: self._normalize_text(summ[i].get("description", ""))
                for lang, summ in summaries.items()
                if i < len(summ)
            }

            # 2. 构建皮肤和炫彩信息
            processed_skins = []
            for i, skin_detail in enumerate(default_details.get("skins", [])):
                skin_id_num = self._parse_skin_id(skin_detail["id"], int(champ_id))
                skin_names = {
                    lang: self._normalize_text(det.get("skins", [])[i].get("name", ""))
                    for lang, det in details.items()
                    if i < len(det.get("skins", []))
                }

                skin_data = {
                    "id": skin_detail["id"],
                    "isBase": skin_detail.get("isBase", False),
                    "skinNames": skin_names,
                    "binPath": f"data/characters/{alias}/skins/skin{skin_id_num}.bin",
                }

                processed_chromas = []
                for j, chroma_detail in enumerate(skin_detail.get("chromas", [])):
                    chroma_id_num = self._parse_skin_id(chroma_detail["id"], int(champ_id))
                    chroma_names = {
                        lang: self._normalize_text(det.get("skins", [])[i].get("chromas", [])[j].get("name", ""))
                        for lang, det in details.items()
                        if i < len(det.get("skins", [])) and j < len(det.get("skins", [])[i].get("chromas", []))
                    }
                    processed_chromas.append(
                        {
                            "id": chroma_detail["id"],
                            "chromaNames": chroma_names,
                            "binPath": f"data/characters/{alias}/skins/skin{chroma_id_num}.bin",
                        }
                    )

                if processed_chromas:
                    skin_data["chromas"] = processed_chromas

                processed_skins.append(skin_data)

            # 3. 组合最终的英雄数据
            final_champions[champ_id] = {
                "id": default_summary["id"],
                "alias": alias,
                "names": names,
                "titles": titles,
                "descriptions": {k: v for k, v in descriptions.items() if v},  # 过滤空描述
                "skins": processed_skins,
                "wad": {
                    "root": f"Game/DATA/FINAL/Champions/{alias}.wad.client",
                    **{
                        lang: f"Game/DATA/FINAL/Champions/{alias}.{lang}.wad.client"
                        for lang in self.process_languages
                        if lang != "default"
                    },
                },
            }
            progress.update()
        progress.finish()

        # 4. 构建最终结果文件
        final_result = {
            "gameVersion": self.version,
            "languages": [lang for lang in self.process_languages if lang != "default"],
            "lastUpdate": datetime.now().isoformat(),
            "indices": {"alias": {champ["alias"].lower(): champ_id for champ_id, champ in final_champions.items()}},
            "champions": final_champions,
        }

        # --- 地图数据处理 ---
        logger.info("合并地图数据...")
        maps_by_lang = self._load_language_json(base_path, "maps.json")
        if "default" in maps_by_lang:
            final_maps = {}
            map_id_to_index_per_lang = {
                lang: {m["id"]: i for i, m in enumerate(maps)} for lang, maps in maps_by_lang.items()
            }

            for default_map in maps_by_lang["default"]:
                map_id = default_map["id"]
                map_string_id = default_map["mapStringId"]

                names = {}
                for lang, maps in maps_by_lang.items():
                    if map_id in map_id_to_index_per_lang.get(lang, {}):
                        idx = map_id_to_index_per_lang[lang][map_id]
                        names[lang] = self._normalize_text(maps[idx]["name"])

                map_data = {"id": map_id, "mapStringId": map_string_id, "names": names}

                # --- WAD信息处理 ---
                wad_prefix = f"Map{map_id}" if map_id != 0 else "Common"
                try:
                    relative_wad_path_base = config.GAME_MAPS_PATH.relative_to(self.game_path).as_posix()
                    wad_path_base = f"{relative_wad_path_base}/{wad_prefix}"

                    # 拼接binPath
                    map_data["binPath"] = f"data/maps/shipping/{wad_prefix.lower()}/{wad_prefix.lower()}.bin"

                    wad_info = {
                        "root": f"{wad_path_base}.wad.client",
                        **{
                            lang: f"{wad_path_base}.{lang}.wad.client"
                            for lang in self.process_languages
                            if lang != "default"
                        },
                    }
                    # 验证文件是否存在
                    if (self.game_path / wad_info["root"]).exists():
                        map_data["wad"] = wad_info
                    else:
                        logger.warning(
                            f"地图 {wad_prefix} 的WAD文件不存在，已跳过: {self.game_path / wad_info['root']}"
                        )
                except ValueError:
                    logger.error("GAME_MAPS_PATH 配置似乎不正确，无法生成相对路径。")

                final_maps[str(map_id)] = map_data
            final_result["maps"] = final_maps
        else:
            logger.warning("未找到default语言的地图数据，跳过处理。")
        # --- 地图数据处理结束 ---

        # 5. 保存
        dump_json(final_result, base_path / "data.json", indent=4 if config.is_dev_mode() else None)

    def _extract_wad_data(self, out_dir: StrPath, region: str) -> None:
        """
        从WAD文件提取JSON数据

        :param out_dir: 输出目录
        :param region: 地区代码
        """
        out_path = Path(out_dir) / self.version / region
        out_path.mkdir(parents=True, exist_ok=True)

        # 处理en_US为default
        _region = "default" if region.lower() == "en_us" else region

        # 获取WAD文件路径
        _head = format_region(_region)
        if _head == "default":
            wad_files = list(self.game_path.glob("LeagueClient/Plugins/rcp-be-lol-game-data/default-assets*.wad"))
        else:
            wad_files = [self.game_path / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data" / f"{_head}-assets.wad"]

        if not wad_files or not wad_files[0].exists():
            logger.error(f"未找到 {_region} 区域的WAD文件")
            return

        # 哈希表
        hash_table = [
            f"plugins/rcp-be-lol-game-data/global/{_region}/v1/champion-summary.json",
            f"plugins/rcp-be-lol-game-data/global/{_region}/v1/skinlines.json",
            f"plugins/rcp-be-lol-game-data/global/{_region}/v1/skins.json",
            f"plugins/rcp-be-lol-game-data/global/{_region}/v1/maps.json",
            f"plugins/rcp-be-lol-game-data/global/{_region}/v1/items.json",
            f"plugins/rcp-be-lol-game-data/global/{_region}/v1/universes.json",
        ]

        # 输出路径转换
        def output_file_name(path: str) -> Path:
            reg = re.compile(rf"plugins/rcp-be-lol-game-data/global/{_region}/v1/", re.IGNORECASE)
            new = reg.sub("", path)
            return out_path / new

        # 解包WAD文件
        for wad_file in wad_files:
            WAD(wad_file).extract(hash_table, output_file_name)

        # 获取英雄概要以解包所有英雄详细信息
        try:
            summary_file = out_path / "champion-summary.json"
            if summary_file.exists():
                with open(summary_file, encoding="utf-8") as f:
                    champions = json.load(f)

                # 提取每个英雄的详细信息
                champion_hashes = [
                    f"plugins/rcp-be-lol-game-data/global/{_region}/v1/champions/{item['id']}.json"
                    for item in champions
                    if item["id"] != -1
                ]

                # 创建champions目录
                (out_path / "champions").mkdir(exist_ok=True)

                # 解包英雄详细信息
                for wad_file in wad_files:
                    WAD(wad_file).extract(champion_hashes, output_file_name)

        except Exception as e:
            logger.error(f"解包英雄信息时出错: {str(e)}")
            if config.is_dev_mode():
                raise

    def _parse_skin_id(self, full_id: int, champion_id: int) -> int:
        """
        从完整的皮肤ID中提取皮肤编号

        :param full_id: 完整ID，如1001
        :param champion_id: 英雄ID，如1
        :return: 皮肤编号，如1
        """
        # 将champion_id转为字符串，计算位数
        champion_id_len = len(str(champion_id))

        # 将完整ID转为字符串，截取champion_id之后的部分
        skin_id_str = str(full_id)[champion_id_len:]

        # 转回整数（会自动去除前导零）
        return int(skin_id_str)


class BinUpdater:
    """
    负责从BIN文件提取音频数据并更新到数据文件中
    """

    def __init__(self, target: str = "all"):
        """
        初始化BIN音频更新器

        :param target: 更新目标, 'skin', 'map', 或 'all'
        """
        self.game_path: Path = config.GAME_PATH
        self.manifest_path: Path = config.MANIFEST_PATH
        if not self.game_path or not self.manifest_path:
            raise ValueError("GAME_PATH 和 MANIFEST_PATH 必须在配置中设置")

        self.target = target
        self.version: str = get_game_version(self.game_path)
        self.version_manifest_path: Path = self.manifest_path / self.version
        self.data_file: Path = self.version_manifest_path / "data.json"
        self.skin_bank_paths_file: Path = self.version_manifest_path / "skins-bank-paths.json"
        self.skin_events_file: Path = self.version_manifest_path / "skins-events.json"
        self.map_bank_paths_file: Path = self.version_manifest_path / "maps-bank-paths.json"
        self.map_events_file: Path = self.version_manifest_path / "maps-events.json"

    def update(self) -> Path | None:
        """
        处理BIN文件，提取皮肤和地图的音频路径和事件数据

        :return: 如果有更新，返回 skin bank paths 数据文件路径, 否则返回 None
        """
        if not self.data_file.exists():
            logger.error(f"数据文件不存在，请先运行DataUpdater: {self.data_file}")
            raise FileNotFoundError(f"数据文件不存在: {self.data_file}")

        try:
            data = load_json(self.data_file)
            if not data:
                logger.error(f"无法加载数据文件: {self.data_file}")
                raise ValueError(f"无法加载或解析JSON文件: {self.data_file}")

            # 根据target决定执行哪些操作
            if self.target in ["skin", "all"]:
                self._update_skins(data)

            if self.target in ["map", "all"]:
                self._update_maps(data)

            logger.success(f"BinUpdater 更新完成 (目标: {self.target})")
            return self.skin_bank_paths_file if self.target in ["skin", "all"] else self.map_bank_paths_file

        except Exception as e:
            logger.error(f"处理BIN文件时出错: {str(e)}")
            if config.is_dev_mode():
                raise
            return None

    def _update_skins(self, data: dict) -> None:
        """处理皮肤数据"""
        logger.info("开始处理皮肤音频数据...")
        # --- 初始化皮肤数据结构 ---
        self.skin_bank_paths_data = {
            "gameVersion": self.version,
            "languages": data.get("languages", []),
            "lastUpdate": datetime.now().isoformat(),
            "skinToChampion": {},
            "championBaseSkins": {},
            "skinAudioMappings": {},
            "skins": {},
        }
        self.skin_events_data = self.skin_bank_paths_data.copy()
        del self.skin_events_data["skinAudioMappings"]
        self.skin_events_data["skins"] = {}

        # --- 处理皮肤数据 ---
        bank_path_to_owner_map: dict[tuple, str] = {}
        champions = data.get("champions", {})
        champion_count = len(champions)
        progress = ProgressTracker(champion_count, "英雄皮肤音频数据处理", log_interval=5)
        sorted_champion_ids = sorted(champions.keys(), key=int)
        for champion_id in sorted_champion_ids:
            champion_data = champions[champion_id]
            self._process_champion_skins(champion_data, champion_id, bank_path_to_owner_map)
            progress.update()
        progress.finish()
        self._optimize_mappings()

        dump_json(self.skin_bank_paths_data, self.skin_bank_paths_file, indent=4 if config.is_dev_mode() else None)
        dump_json(self.skin_events_data, self.skin_events_file, indent=4 if config.is_dev_mode() else None)
        logger.success("皮肤数据更新完成")

    def _update_maps(self, data: dict) -> None:
        """处理地图数据"""
        logger.info("开始处理地图音频数据...")
        # --- 初始化地图数据结构 ---
        self.map_bank_paths_data = {
            "gameVersion": self.version,
            "languages": data.get("languages", []),
            "lastUpdate": datetime.now().isoformat(),
            "maps": {},
        }
        self.map_events_data = self.map_bank_paths_data.copy()
        self.map_events_data["maps"] = {}

        # --- 处理地图数据 ---
        maps = data.get("maps", {})
        map_progress = ProgressTracker(len(maps), "地图音频数据处理", log_interval=1)
        for map_data in maps.values():
            self._process_map_bin(map_data)
            map_progress.update()
        map_progress.finish()

        dump_json(self.map_bank_paths_data, self.map_bank_paths_file, indent=4 if config.is_dev_mode() else None)
        dump_json(self.map_events_data, self.map_events_file, indent=4 if config.is_dev_mode() else None)
        logger.success("地图数据更新完成")

    def _process_champion_skins(
        self, champion_data: ChampionData, champion_id: str, bank_path_to_owner_map: dict
    ) -> None:
        """
        处理单个英雄的所有皮肤，提取音频数据并建立映射关系

        :param champion_data: 英雄数据
        :param champion_id: 英雄ID
        :param bank_path_to_owner_map: 全局资源注册表
        """
        alias = champion_data.get("alias", "").lower()
        if not alias:
            return

        # 1. 收集所有皮肤和炫彩的BIN文件路径，并创建 path -> skin_id 的映射
        path_to_skin_id_map: dict[str, str] = {}
        skins_data = champion_data.get("skins", [])
        # 按皮肤ID排序，确保基础皮肤优先处理
        sorted_skins_data = sorted(skins_data, key=lambda s: int(s["id"]))

        base_skin_id = None
        for skin in sorted_skins_data:
            skin_id_str = str(skin["id"])
            # 建立 skin -> champion 索引
            self.skin_bank_paths_data["skinToChampion"][skin_id_str] = champion_id
            self.skin_events_data["skinToChampion"][skin_id_str] = champion_id
            if skin.get("isBase"):
                base_skin_id = skin_id_str
                # 建立 champion -> base_skin 索引
                self.skin_bank_paths_data["championBaseSkins"][champion_id] = base_skin_id
                self.skin_events_data["championBaseSkins"][champion_id] = base_skin_id

            if bin_path := skin.get("binPath"):
                path_to_skin_id_map[bin_path] = skin_id_str
            for chroma in skin.get("chromas", []):
                chroma_id_str = str(chroma["id"])
                self.skin_bank_paths_data["skinToChampion"][chroma_id_str] = champion_id
                self.skin_events_data["skinToChampion"][chroma_id_str] = champion_id
                if bin_path := chroma.get("binPath"):
                    path_to_skin_id_map[bin_path] = chroma_id_str

        if not path_to_skin_id_map:
            return

        # 2. 一次性从WAD文件中提取所有相关的BIN文件原始数据
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

        # 3. 按皮肤ID顺序处理每个皮肤的BIN文件
        skin_ids_sorted = sorted(path_to_skin_id_map.values(), key=int)
        path_to_id_reversed = {v: k for k, v in path_to_skin_id_map.items()}

        for skin_id in skin_ids_sorted:
            path = path_to_id_reversed[skin_id]
            if not (bin_raw := raw_data_map.get(path)):
                continue

            try:
                bin_file = BIN(bin_raw)
                is_new_skin_entry = True  # 标记是否是该皮肤的第一个被认领的资源

                for group in bin_file.data:
                    for event_data in group.bank_units:
                        # bank path 处理
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

                                # --- 事件数据处理 ---
                                # 只有当bank path被认领时，才提取相关的事件数据
                                if is_new_skin_entry:
                                    self._extract_skin_events(skin_id, bin_file, base_skin_id)
                                    is_new_skin_entry = False

            except Exception as e:
                logger.error(f"解析皮肤BIN失败: {path}, 错误: {e}")
                if config.is_dev_mode():
                    raise

    def _extract_skin_events(self, skin_id: str, bin_file: BIN, base_skin_id: str | None) -> None:
        """
        提取一个皮肤BIN文件中的所有事件数据

        :param skin_id: 皮肤ID
        :param bin_file: BIN文件对象
        :param base_skin_id: 该英雄的基础皮肤ID
        """
        skin_events = {}
        if bin_file.theme_music:
            skin_events["theme_music"] = bin_file.theme_music

        all_events_by_category = {}
        for group in bin_file.data:
            if group.music:
                skin_events["music"] = group.music.to_dict()
            for event_data in group.bank_units:
                if base_skin_id and skin_id != base_skin_id and "_Base_" in event_data.category:
                    continue
                if event_data.events:
                    category = event_data.category
                    if category not in all_events_by_category:
                        all_events_by_category[category] = []
                    all_events_by_category[category].extend([e.to_dict() for e in event_data.events])

        if all_events_by_category:
            skin_events["events"] = all_events_by_category

        if skin_events:
            self.skin_events_data["skins"][skin_id] = skin_events

    def _process_map_bin(self, map_data: dict) -> None:
        """
        处理单个地图的BIN文件，提取bank paths和事件数据

        :param map_data: 地图数据
        """
        map_id = str(map_data["id"])

        if not map_data.get("wad") or not map_data.get("binPath"):
            logger.debug(f"地图 {map_id} 缺少 WAD 或 binPath 信息，已跳过。")
            return

        wad_path = self.game_path / map_data["wad"]["root"]
        bin_path = map_data["binPath"]

        if not wad_path.exists():
            logger.warning(f"地图 {map_id} 的WAD文件不存在，已跳过: {wad_path}")
            return

        try:
            logger.debug(f"正在提取地图 {map_id} 的BIN文件: {bin_path}")
            bin_raws = WAD(wad_path).extract([bin_path], raw=True)
            if not bin_raws or not bin_raws[0]:
                logger.warning(f"从地图 {map_id} 的WAD文件中未能提取到有效的BIN数据。")
                return
            bin_file = BIN(bin_raws[0])
        except Exception as e:
            logger.error(f"提取或解析地图 {map_id} 的BIN文件时出错: {e}")
            if config.is_dev_mode():
                raise
            return

        # --- 提取 Bank Paths ---
        map_bank_paths = {}
        for group in bin_file.data:
            for event_data in group.bank_units:
                if event_data.bank_path:
                    category = event_data.category
                    if category not in map_bank_paths:
                        map_bank_paths[category] = []
                    map_bank_paths[category].append(event_data.bank_path)
        if map_bank_paths:
            self.map_bank_paths_data["maps"][map_id] = map_bank_paths

        # --- 提取 Events ---
        self._extract_map_events(map_id, bin_file)

    def _extract_map_events(self, map_id: str, bin_file: BIN) -> None:
        """
        提取一个地图BIN文件中的所有事件数据

        :param map_id: 地图ID
        :param bin_file: BIN文件对象
        """
        map_events = {}
        if bin_file.theme_music:
            map_events["theme_music"] = bin_file.theme_music

        all_events_by_category = {}
        for group in bin_file.data:
            if group.music:
                map_events["music"] = group.music.to_dict()
            for event_data in group.bank_units:
                if event_data.events:
                    category = event_data.category
                    if category not in all_events_by_category:
                        all_events_by_category[category] = []
                    all_events_by_category[category].extend([e.to_dict() for e in event_data.events])

        if all_events_by_category:
            map_events["events"] = all_events_by_category

        if map_events:
            self.map_events_data["maps"][map_id] = map_events

    def _optimize_mappings(self) -> None:
        """
        优化映射关系，将部分共享升级为完全共享
        """
        for skin_id, mappings in self.skin_bank_paths_data["skinAudioMappings"].copy().items():
            if not isinstance(mappings, dict):
                continue

            # 获取该皮肤所有共享资源的来源ID
            owner_ids = set(mappings.values())

            # 如果所有共享资源都来自同一个源皮肤，则升级为完全共享
            if len(owner_ids) == 1:
                owner_id = owner_ids.pop()
                # 检查该皮肤是否还有自己的独立音频，如果没有，才能安全升级
                if skin_id not in self.skin_bank_paths_data["skins"]:
                    self.skin_bank_paths_data["skinAudioMappings"][skin_id] = owner_id


class DataReader(metaclass=Singleton):
    """
    从合并后的数据文件读取游戏数据
    """

    # 音频类型常量定义 (与BinUpdater保持一致)
    AUDIO_TYPE_SFX = "SFX"
    AUDIO_TYPE_VO = "VO"
    AUDIO_TYPE_SFX_OUTOFGAME = "SFX_OutOfGame"
    AUDIO_TYPE_VO_OUTOFGAME = "VO_OutOfGame"
    AUDIO_TYPE_REWORK_SFX = "Rework_SFX"

    KNOWN_AUDIO_TYPES = {
        AUDIO_TYPE_SFX,
        AUDIO_TYPE_VO,
        AUDIO_TYPE_SFX_OUTOFGAME,
        AUDIO_TYPE_VO_OUTOFGAME,
        AUDIO_TYPE_REWORK_SFX,
    }

    def __init__(self, default_language: str = "default"):
        """
        初始化数据读取器

        :param default_language: 默认使用的语言
        """
        # 防止单例被重复初始化
        if hasattr(self, "initialized"):
            return

        self.game_path: Path = config.GAME_PATH
        self.manifest_path: Path = config.MANIFEST_PATH
        if not self.game_path or not self.manifest_path:
            raise ValueError("GAME_PATH 和 MANIFEST_PATH 必须在配置中设置")

        self.version: str = get_game_version(self.game_path)
        self.version_manifest_path: Path = self.manifest_path / self.version

        data_file = self.version_manifest_path / "data.json"
        bank_paths_file = self.version_manifest_path / "skins-bank-paths.json"
        events_file = self.version_manifest_path / "skins-events.json"

        self.data = self._load_data(data_file)
        self.bin_data = self._load_data(bank_paths_file)  # DataReader主要还是用bank_path的数据
        self.events_data = self._load_data(events_file)
        self.default_language = default_language
        self.initialized = True

    def _load_data(self, data_file: StrPath) -> dict:
        """
        加载数据文件

        :param data_file: JSON数据文件路径
        :return: 加载的数据
        """
        path = Path(data_file)
        if not path.exists():
            logger.warning(f"数据文件不存在: {data_file}，将返回空字典")
            return {}

        data = load_json(path)
        if not data:
            logger.error(f"无法加载数据文件: {data_file}")
            return {}
        return data

    def set_language(self, language: str) -> None:
        """
        设置默认语言

        :param language: 语言代码
        """
        self.default_language = language

    def get_audio_type(self, category: str) -> str:
        """
        从分类字符串中提取音频类型标识

        :param category: 原始分类字符串(如'Aatrox_Base_SFX')
        :return: 音频类型标识(如'SFX'或'SFX_OutOfGame')
        """
        parts = category.split("_")
        if len(parts) < 3:
            return "unknown"

        # 特殊情况处理: Skarner重做
        if parts[0] == "Skarner" and parts[1] == "Rework" and len(parts) >= 4:
            return self.AUDIO_TYPE_REWORK_SFX

        # 通常格式为 [英雄名]_[皮肤]_[类型] 或 [英雄名]_[皮肤]_[类型]_[子类型]
        if len(parts) >= 4:
            potential_compound_type = "_".join(parts[2:])
            if potential_compound_type in self.KNOWN_AUDIO_TYPES:
                return potential_compound_type

        _type = parts[2]
        return _type if _type in self.KNOWN_AUDIO_TYPES else "unknown"

    def get_languages(self) -> list[str]:
        """
        获取支持的语言列表

        :return: 语言代码列表
        """
        # 优先使用预计算的languages字段
        if "languages" in self.data:
            languages = set(self.data["languages"])
            languages.add("default")  # 确保default始终存在
            return list(languages)

        # 备选：从英雄数据中收集语言
        languages = set()
        for champion in self.data.get("champions", {}).values():
            languages.update(champion.get("names", {}).keys())
        return list(languages)

    def get_skin_bank(self, skin_id: int) -> dict:
        """
        根据皮肤ID获取音频资源集合数据

        :param skin_id: 皮肤ID
        :return: 音频数据
        """
        skin_id_str = str(skin_id)
        mappings = self.bin_data.get("skinAudioMappings", {})
        skins_data = self.bin_data.get("skins", {})

        # 1. 检查是否存在完全重定向映射
        mapping_info = mappings.get(skin_id_str)
        if isinstance(mapping_info, str):
            # 递归调用以处理可能的链式映射
            return self.get_skin_bank(int(mapping_info))

        # 2. 获取基础皮肤的音频数据作为底座
        result = {}
        champion_id = self.bin_data.get("skinToChampion", {}).get(skin_id_str)
        if champion_id:
            base_skin_id = self.bin_data.get("championBaseSkins", {}).get(champion_id)
            if base_skin_id:
                result = skins_data.get(base_skin_id, {}).copy()

        # 3. 合并当前皮肤自己的独立音频数据
        if skin_data := skins_data.get(skin_id_str):
            result.update(skin_data)

        # 4. 合并部分共享的音频数据
        if isinstance(mapping_info, dict):
            for category, owner_id in mapping_info.items():
                owner_data = skins_data.get(owner_id, {})
                if category in owner_data:
                    result[category] = owner_data[category]

        return result

    def get_champion(self, champion_id: int) -> dict:
        """
        根据ID获取英雄信息

        :param champion_id: 英雄ID
        :return: 英雄信息
        """
        champ_id = str(champion_id)
        return self.data.get("champions", {}).get(champ_id, {})

    def find_champion(self, alias: str) -> dict:
        """
        根据别名获取英雄信息

        :param alias: 英雄别名
        :return: 英雄信息
        """
        # 使用索引查找
        if "indices" in self.data and "alias" in self.data.get("indices", {}):
            champ_id = self.data["indices"]["alias"].get(alias.lower())
            if champ_id:
                return self.data.get("champions", {}).get(champ_id, {})

        # 索引不存在或未找到，回退到传统查找方式
        for champion in self.data.get("champions", {}).values():
            if champion.get("alias", "").lower() == alias.lower():
                return champion
        return {}

    def get_champions(self) -> list[dict]:
        """
        获取所有英雄列表

        :return: 英雄列表
        """
        return list(self.data.get("champions", {}).values())
