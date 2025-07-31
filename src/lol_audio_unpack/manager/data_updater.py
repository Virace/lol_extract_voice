# 🐍 Sparse is better than dense.
# 🐼 稀疏优于稠密
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2025/7/30 7:39
# @Update  : 2025/7/31 20:20
# @Detail  : 数据更新器


import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from league_tools.formats import WAD
from loguru import logger

from lol_audio_unpack.manager.utils import (
    get_game_version,
    needs_update,
    read_data,
    write_data,
)
from lol_audio_unpack.utils.common import format_region, load_json
from lol_audio_unpack.utils.config import config
from lol_audio_unpack.utils.type_hints import StrPath


class DataUpdater:
    """
    负责游戏数据的更新和多语言JSON合并
    """

    def __init__(self, languages: list[str] | None = None, force_update: bool = False) -> None:
        """
        初始化数据更新器

        :param languages: 需要处理的语言列表（不包括default，default会自动添加）。
                        如果为None，则使用config中的GAME_REGION。
        :param force_update: 是否强制更新
        """
        self.game_path: Path = config.GAME_PATH
        self.manifest_path: Path = config.MANIFEST_PATH
        self.temp_path: Path = config.TEMP_PATH

        if not self.game_path or not self.manifest_path:
            raise ValueError("GAME_PATH 和 MANIFEST_PATH 必须在配置中设置")

        if languages is None:
            game_region = config.GAME_REGION or "zh_CN"
            self.languages: list[str] = [game_region]
        else:
            self.languages: list[str] = languages

        self.version: str = get_game_version(self.game_path)
        self.version_manifest_path: Path = self.manifest_path / self.version
        self.data_file_base: Path = self.version_manifest_path / "data"
        self.process_languages: list[str] = self._prepare_language_list(self.languages)
        self.force_update = force_update

        self.version_manifest_path.mkdir(parents=True, exist_ok=True)

    def _prepare_language_list(self, languages: list[str]) -> list[str]:
        """准备处理语言列表，确保default在列表中"""
        process_languages = ["default"]
        for lang in languages:
            if lang.lower() not in ["default", "en_us"]:
                process_languages.append(lang)
        return process_languages

    @staticmethod
    def _normalize_text(text: str) -> str:
        """标准化文本"""
        if not isinstance(text, str):
            return text
        return text.replace("\u00a0", " ")

    def check_and_update(self) -> Path:
        """检查游戏版本并更新数据"""
        if not needs_update(self.data_file_base, self.version, self.force_update) and self._check_languages():
            logger.info(f"数据文件已是最新版本 {self.version} 且包含所有请求的语言，无需更新。")
            # 返回基础路径，让调用者决定使用哪个具体文件
            return self.data_file_base

        run_temp_path = self.temp_path / f"update_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        run_temp_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"创建临时目录用于解包: {run_temp_path}")

        try:
            self._process_data(run_temp_path)
            # 成功后，日志记录的是yml或msgpack的实际路径
            fmt = "yml" if config.is_dev_mode() else "msgpack"
            logger.success(f"数据更新完成: {self.data_file_base.with_suffix(f'.{fmt}')}")
            return self.data_file_base
        finally:
            if not config.is_dev_mode():
                try:
                    shutil.rmtree(run_temp_path)
                    logger.info(f"已清理临时目录: {run_temp_path}")
                except OSError as e:
                    logger.error(f"清理临时目录失败: {run_temp_path}, error: {e}")
            else:
                logger.warning(f"开发模式，临时目录未删除: {run_temp_path}")

    def _check_languages(self) -> bool:
        """检查现有数据文件是否包含所有请求的语言"""
        data = read_data(self.data_file_base)
        if not data:
            return False

        existing_languages = set(data.get("languages", []))
        existing_languages.add("default")
        requested_languages = set(self.process_languages)

        if requested_languages.issubset(existing_languages):
            return True
        else:
            missing_langs = requested_languages - existing_languages
            logger.info(f"需要更新数据文件，缺少语言: {missing_langs}")
            return False

    def _process_data(self, temp_path: Path) -> None:
        """处理游戏数据，包括提取、合并和验证"""

        for language in self.process_languages:
            logger.info(f"正在处理 {language} 语言数据...")
            self._extract_wad_data(temp_path, language)

        logger.info("合并多语言数据...")
        self._merge_and_build_data(temp_path)

        # 从临时目录复制最终生成的数据文件到目标目录
        temp_data_file_base = temp_path / self.version / "data"
        fmt = "yml" if config.is_dev_mode() else "msgpack"
        source_file = temp_data_file_base.with_suffix(f".{fmt}")

        if source_file.exists():
            self.version_manifest_path.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, self.data_file_base.with_suffix(f".{fmt}"))
            logger.info(f"已复制合并数据到: {self.data_file_base.with_suffix(f'.{fmt}')}")
        else:
            raise FileNotFoundError(f"未能创建合并数据文件: {source_file}")

    def _load_language_json(self, base_path: Path, filename_template: str) -> dict[str, Any]:
        """加载指定模板的、所有语言的JSON文件"""
        loaded_data = {}
        for lang in self.process_languages:
            file_path = base_path / lang / filename_template.format(lang=lang)
            if file_path.exists():
                # 这里读取的是WAD解包出的原始json，所以必须用load_json
                loaded_data[lang] = load_json(file_path)
            else:
                logger.warning(f"未找到JSON文件: {file_path}")
        return loaded_data

    def _merge_and_build_data(self, temp_dir: Path) -> None:
        """聚合所有数据处理和合并逻辑"""
        base_path = temp_dir / self.version
        summaries = self._load_language_json(base_path, "champion-summary.json")

        if "default" not in summaries:
            logger.error("未找到default语言的英雄概要数据，无法继续处理")
            return

        final_champions = {}

        for i, default_summary in enumerate(summaries["default"]):
            champ_id = str(default_summary["id"])
            if champ_id == "-1":
                continue

            alias = self._normalize_text(default_summary["alias"])
            details = self._load_language_json(base_path, f"champions/{champ_id}.json")
            default_details = details.get("default", {})

            names = {lang: self._normalize_text(summ[i]["name"]) for lang, summ in summaries.items() if i < len(summ)}
            titles = {lang: self._normalize_text(det.get("title", "")) for lang, det in details.items()}
            descriptions = {
                lang: self._normalize_text(summ[i].get("description", ""))
                for lang, summ in summaries.items()
                if i < len(summ)
            }

            processed_skins = []
            for skin_idx, skin_detail in enumerate(default_details.get("skins", [])):
                skin_id_num = self._parse_skin_id(skin_detail["id"], int(champ_id))
                skin_names = {
                    lang: self._normalize_text(det.get("skins", [])[skin_idx].get("name", ""))
                    for lang, det in details.items()
                    if skin_idx < len(det.get("skins", []))
                }

                skin_data = {
                    "id": skin_detail["id"],
                    "isBase": skin_detail.get("isBase", False),
                    "skinNames": skin_names,
                    "binPath": f"data/characters/{alias}/skins/skin{skin_id_num}.bin",
                }

                processed_chromas = []
                for chroma_idx, chroma_detail in enumerate(skin_detail.get("chromas", [])):
                    chroma_id_num = self._parse_skin_id(chroma_detail["id"], int(champ_id))
                    chroma_names = {
                        lang: self._normalize_text(
                            det.get("skins", [])[skin_idx].get("chromas", [])[chroma_idx].get("name", "")
                        )
                        for lang, det in details.items()
                        if skin_idx < len(det.get("skins", []))
                        and chroma_idx < len(det.get("skins", [])[skin_idx].get("chromas", []))
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

            final_champions[champ_id] = {
                "id": default_summary["id"],
                "alias": alias,
                "names": names,
                "titles": titles,
                "descriptions": {k: v for k, v in descriptions.items() if v},
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

        final_result = {
            "gameVersion": self.version,
            "languages": [lang for lang in self.process_languages if lang != "default"],
            "lastUpdate": datetime.now().isoformat(),
            "champions": final_champions,
        }

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

                wad_prefix = f"Map{map_id}" if map_id != 0 else "Common"
                try:
                    relative_wad_path_base = config.GAME_MAPS_PATH.relative_to(self.game_path).as_posix()
                    wad_path_base = f"{relative_wad_path_base}/{wad_prefix}"
                    map_data["binPath"] = f"data/maps/shipping/{wad_prefix.lower()}/{wad_prefix.lower()}.bin"
                    wad_info = {
                        "root": f"{wad_path_base}.wad.client",
                        **{
                            lang: f"{wad_path_base}.{lang}.wad.client"
                            for lang in self.process_languages
                            if lang != "default"
                        },
                    }
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

        # 根据环境写入最佳格式
        write_data(final_result, base_path / "data")

    def _extract_wad_data(self, out_dir: StrPath, region: str) -> None:
        """从WAD文件提取JSON数据"""
        out_path = Path(out_dir) / self.version / region
        out_path.mkdir(parents=True, exist_ok=True)
        _region = "default" if region.lower() == "en_us" else region
        _head = format_region(_region)
        if _head == "default":
            wad_files = list(self.game_path.glob("LeagueClient/Plugins/rcp-be-lol-game-data/default-assets*.wad"))
        else:
            wad_files = [self.game_path / "LeagueClient" / "Plugins" / f"rcp-be-lol-game-data/{_head}-assets.wad"]

        if not wad_files or not all(f.exists() for f in wad_files):
            logger.error(f"未找到 {_region} 区域的WAD文件")
            return

        hash_table = [
            f"plugins/rcp-be-lol-game-data/global/{_region}/v1/champion-summary.json",
            f"plugins/rcp-be-lol-game-data/global/{_region}/v1/maps.json",
        ]

        def output_file_name(path: str) -> Path:
            # 修正正则表达式以匹配更通用的路径
            reg = re.compile(rf"plugins/rcp-be-lol-game-data/global/{_region}/v\d+/", re.IGNORECASE)
            new = reg.sub("", path)
            return out_path / new

        for wad_file in wad_files:
            WAD(wad_file).extract(hash_table, output_file_name)

        try:
            summary_file = out_path / "champion-summary.json"
            if summary_file.exists():
                champions = load_json(summary_file)
                champion_hashes = [
                    f"plugins/rcp-be-lol-game-data/global/{_region}/v1/champions/{item['id']}.json"
                    for item in champions
                    if item["id"] != -1
                ]
                (out_path / "champions").mkdir(exist_ok=True)
                for wad_file in wad_files:
                    WAD(wad_file).extract(champion_hashes, output_file_name)
        except Exception as e:
            logger.error(f"解包英雄信息时出错: {str(e)}")
            if config.is_dev_mode():
                raise

    def _parse_skin_id(self, full_id: int, champion_id: int) -> int:
        """从完整的皮肤ID中提取皮肤编号"""
        champion_id_len = len(str(champion_id))
        skin_id_str = str(full_id)[champion_id_len:]
        return int(skin_id_str)
