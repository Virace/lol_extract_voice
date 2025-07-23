# 🐍 Explicit is better than implicit.
# 🐼 明了优于隐晦
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2024/5/6 1:19
# @Update  : 2025/7/24 5:32
# @Detail  : 游戏数据管理器


import json
import re
import shutil
import tempfile
import traceback
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import requests
from league_tools.formats import BIN, WAD
from loguru import logger

from lol_audio_unpack.Utils.common import Singleton, format_region
from lol_audio_unpack.Utils.type_hints import StrPath


class GameDataUpdater:
    """
    负责游戏数据的更新和多语言JSON合并
    """

    @staticmethod
    def check_and_update(game_path: StrPath, out_dir: StrPath, languages=None) -> Path:
        """
        检查游戏版本并更新数据

        :param game_path: 游戏路径
        :param out_dir: 输出目录
        :param languages: 需要处理的语言列表（不包括default，default会自动添加）
        :return: 合并后的数据文件路径
        """
        # 默认语言设置
        if languages is None:
            languages = ["zh_CN"]

        # 确保default语言在处理列表中（default是必须的，作为基础参照）
        process_languages = ["default"]
        for lang in languages:
            if lang.lower() != "default" and lang.lower() != "en_us":
                process_languages.append(lang)

        # 获取游戏版本
        version = GameDataUpdater._get_game_version(game_path)

        # 检查输出目录并创建
        out_path = Path(out_dir) / version
        out_path.mkdir(parents=True, exist_ok=True)

        # 合并后的数据文件路径
        merged_file = out_path / "merged_data.json"

        # 检查是否需要更新：1.文件是否存在 2.请求的语言是否都已包含
        needs_update = True
        if merged_file.exists():
            try:
                with open(merged_file, encoding="utf-8") as f:
                    existing_data = json.load(f)

                # 检查现有文件包含的语言
                existing_languages = set(existing_data.get("languages", []))
                existing_languages.add("default")  # default总是包含的

                # 检查请求的所有语言是否都已包含
                requested_languages = set(process_languages)

                # 如果所有请求的语言都已包含在现有文件中，则不需要更新
                if requested_languages.issubset(existing_languages):
                    logger.info(f"数据文件已是最新版本 {version}，且包含所有请求的语言")
                    needs_update = False
                else:
                    missing_langs = requested_languages - existing_languages
                    logger.info(f"需要更新数据文件，缺少语言: {missing_langs}")
            except Exception as e:
                logger.error(f"检查现有数据文件时出错: {str(e)}")
                # 出错时默认需要更新

        if not needs_update:
            return merged_file

        # 创建临时目录
        with tempfile.TemporaryDirectory(prefix="lol_data_", delete=True) as temp_dir:
            temp_path = Path(temp_dir)
            logger.info(f"创建临时目录用于解包: {temp_path}")

            # 提取需要的数据
            for language in process_languages:
                logger.info(f"正在处理 {language} 语言数据...")
                GameDataUpdater._extract_wad_data(game_path, temp_path, language, version)

            # 合并多语言数据
            logger.info("合并多语言数据...")
            GameDataUpdater._merge_language_data(temp_path, version, process_languages)

            # 验证WAD文件是否存在并更新路径信息
            logger.info("验证WAD文件路径...")
            GameDataUpdater._verify_wad_paths(game_path, temp_path, version)

            # 处理BIN文件，提取音频路径
            logger.info("处理BIN文件，提取音频路径...")
            GameDataUpdater._process_bin_files(game_path, temp_path, version)

            # 将合并后的数据文件复制到输出目录
            temp_merged_file = temp_path / version / "merged_data.json"
            if temp_merged_file.exists():
                out_path.mkdir(parents=True, exist_ok=True)
                shutil.copy2(temp_merged_file, merged_file)
                logger.info(f"已复制合并数据到: {merged_file}")
            else:
                raise FileNotFoundError(f"未能创建合并数据文件: {temp_merged_file}")

        # 临时目录会自动删除
        logger.info("临时文件已清理")
        logger.success(f"数据更新完成: {merged_file}")
        return merged_file

    @staticmethod
    def _process_bin_files(game_path: StrPath, out_dir: StrPath, version: str) -> None:
        """
        处理BIN文件，提取音频路径并添加到皮肤数据中

        :param game_path: 游戏路径
        :param out_dir: 输出目录
        :param version: 游戏版本
        """
        game_path = Path(game_path)
        merged_file = Path(out_dir) / version / "merged_data.json"

        if not merged_file.exists():
            logger.error(f"合并数据文件不存在: {merged_file}")
            return

        try:
            with open(merged_file, encoding="utf-8") as f:
                data = json.load(f)

            # 创建临时目录存放提取的BIN文件
            temp_bin_dir = Path(out_dir) / "bin_temp"
            temp_bin_dir.mkdir(parents=True, exist_ok=True)

            # 遍历所有英雄
            for champion_id, champion_data in data.get("champions", {}).items():
                if "wad" not in champion_data or "skins" not in champion_data:
                    continue

                alias = champion_data.get("alias", "").lower()
                if not alias:
                    continue

                # 获取基础WAD路径
                root_wad_path = champion_data["wad"].get("root")
                if not root_wad_path:
                    continue

                full_wad_path = game_path / root_wad_path
                if not full_wad_path.exists():
                    logger.error(f"英雄 {alias} 的WAD文件不存在: {full_wad_path}")
                    continue

                # 构造所有皮肤的BIN文件路径
                bin_paths = []
                skin_ids = []

                for skin in champion_data.get("skins", []):
                    # 提取皮肤ID
                    skin_id = GameDataUpdater._extract_skin_id_from_full_id(skin.get("id"), int(champion_id))
                    skin_ids.append(skin_id)
                    bin_paths.append(f"data/characters/{alias}/skins/skin{skin_id}.bin")

                if not bin_paths:
                    continue

                # 从WAD中提取BIN文件
                logger.info(f"从 {full_wad_path} 提取 {len(bin_paths)} 个BIN文件")

                categories = []

                try:
                    # 提取BIN文件
                    bin_raws = WAD(full_wad_path).extract(bin_paths, raw=True)

                    for i in range(len(bin_raws)):
                        bin_raw = bin_raws[i]
                        if not bin_raw:
                            continue

                        bin_file = BIN(bin_raw)
                        for entry in bin_file.data:
                            for bank in entry.bank_units:
                                if bank.category not in categories:
                                    categories.append(bank.category)
                                    _type = bank.category.split("_")[-1]
                                    champion_data["skins"][i]["audio_data"][_type] = bank.bank_path

                except Exception as e:
                    logger.error(f"处理英雄 {alias} 的BIN文件时出错: {str(e)}")
                    logger.debug(traceback.format_exc())

            # 保存更新后的数据
            with open(merged_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)

            # 清理临时目录
            shutil.rmtree(temp_bin_dir, ignore_errors=True)

        except Exception as e:
            logger.error(f"处理BIN文件时出错: {str(e)}")
            logger.debug(traceback.format_exc())

    @staticmethod
    def _extract_skin_id_from_full_id(full_id: int, champion_id: int) -> int:
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

    @staticmethod
    def _get_game_version(game_path: StrPath) -> str:
        """
        获取游戏版本

        :param game_path: 游戏路径
        :return: 游戏版本号
        """
        meta = Path(game_path) / "Game" / "content-metadata.json"
        if not meta.exists():
            raise FileNotFoundError("content-metadata.json 文件不存在，无法判断版本信息")

        with open(meta, encoding="utf-8") as f:
            data = json.load(f)

        version_v = data["version"]

        if m := re.match(r"^(\d+\.\d+)\.", version_v):
            return m.group(1)

        raise ValueError(f"无法解析版本号: {version_v}")

    @staticmethod
    def _extract_wad_data(game_path: StrPath, out_dir: StrPath, region: str, version: str) -> None:
        """
        从WAD文件提取JSON数据

        :param game_path: 游戏路径
        :param out_dir: 输出目录
        :param region: 地区代码
        :param version: 游戏版本
        """
        game_path = Path(game_path)
        out_path = Path(out_dir) / version / region
        out_path.mkdir(parents=True, exist_ok=True)

        # 处理en_US为default
        _region = region
        if region.lower() == "en_us":
            _region = "default"

        # 获取WAD文件路径
        _head = format_region(_region)
        if _head == "default":
            wad_files = list(game_path.glob("LeagueClient/Plugins/rcp-be-lol-game-data/default-assets*.wad"))
        else:
            wad_files = [game_path / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data" / f"{_head}-assets.wad"]

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
            logger.debug(traceback.format_exc())

    @staticmethod
    def _merge_language_data(out_dir: StrPath, version: str, languages: list[str]) -> None:
        """
        合并多种语言的JSON数据

        :param out_dir: 输出目录基础路径
        :param version: 游戏版本
        :param languages: 语言列表
        """
        base_path = Path(out_dir) / version

        # 确保default在语言列表中
        if "default" not in languages:
            logger.error("语言列表必须包含'default'")
            return

        # 第一步：读取所有语言的champion-summary.json
        champion_summaries = GameDataUpdater._load_language_summaries(base_path, languages)

        # 如果没有找到default语言的数据，无法继续
        if "default" not in champion_summaries:
            logger.error("未找到default语言的英雄概要数据，无法处理")
            return

        # 检查各个语言文件的字段情况
        field_availability = GameDataUpdater._analyze_field_availability(champion_summaries)

        # 初始化结果结构
        result = GameDataUpdater._initialize_result_structure(version)

        # 处理default语言的英雄数据
        GameDataUpdater._process_default_champions(result, champion_summaries["default"], field_availability, base_path)

        # 处理其他语言的数据
        for language in languages:
            if language != "default" and language.lower() != "en_us" and language in champion_summaries:
                GameDataUpdater._process_other_language_data(
                    result, champion_summaries[language], field_availability, base_path, language
                )

        # 创建索引并完成结果
        final_result = GameDataUpdater._finalize_result(result, languages)

        # 保存合并后的数据
        merged_file = base_path / "merged_data.json"
        with open(merged_file, "w", encoding="utf-8") as f:
            json.dump(final_result, f, ensure_ascii=False)

    @staticmethod
    def _load_language_summaries(base_path: Path, languages: list[str]) -> dict[str, list]:
        """
        读取所有语言的英雄概要数据

        :param base_path: 基础路径
        :param languages: 语言列表
        :return: 各语言的英雄概要数据
        """
        champion_summaries = {}
        for language in languages:
            lang_code = "default" if language.lower() == "en_us" else language
            lang_path = base_path / lang_code
            summary_file = lang_path / "champion-summary.json"

            if summary_file.exists():
                try:
                    with open(summary_file, encoding="utf-8") as f:
                        champion_summaries[lang_code] = json.load(f)
                        logger.info(f"已加载 {lang_code} 语言的英雄概要，{len(champion_summaries[lang_code])} 个英雄")
                except Exception as e:
                    logger.error(f"读取 {lang_code} 语言英雄概要失败: {str(e)}")

        return champion_summaries

    @staticmethod
    def _analyze_field_availability(champion_summaries: dict[str, list]) -> dict[str, set]:
        """
        分析各语言文件的字段可用性

        :param champion_summaries: 各语言的英雄概要数据
        :return: 各语言可用字段的集合
        """
        field_availability = {}
        for lang, champions in champion_summaries.items():
            # 用第一个英雄作为检查样本
            if champions and len(champions) > 0:
                sample_champion = champions[0]
                fields = set(sample_champion.keys())
                field_availability[lang] = fields
                logger.debug(f"{lang} 语言的champion字段: {fields}")
        return field_availability

    @staticmethod
    def _initialize_result_structure(version: str) -> dict:
        """
        初始化结果数据结构

        :param version: 游戏版本
        :return: 初始化的结果字典
        """
        return {
            "indices": {},  # 先预留索引位置
            "champions": {},
            "gameVersion": version,
            "lastUpdate": datetime.now().isoformat(),
        }

    @staticmethod
    def _process_default_champions(
        result: dict, default_champions: list, field_availability: dict[str, set], base_path: Path
    ) -> None:
        """
        处理default语言的英雄数据

        :param result: 结果数据结构
        :param default_champions: default语言的英雄数据
        :param field_availability: 字段可用性信息
        :param base_path: 基础路径
        """
        default_path = base_path / "default" / "champions"

        # 检查默认语言中是否有description字段
        has_description = "description" in field_availability.get("default", set())

        # 遍历default语言的所有英雄
        for champion in default_champions:
            if champion["id"] == -1:  # 跳过"无"英雄
                continue

            champ_id = str(champion["id"])

            # 创建英雄基本结构
            result["champions"][champ_id] = {
                "id": champion["id"],
                "alias": champion["alias"],
                # "contentId": champion["contentId"],
                "names": {"default": champion["name"]},
            }

            # 仅在默认语言有description字段时添加
            if has_description and "description" in champion:
                result["champions"][champ_id]["descriptions"] = {"default": champion["description"]}

            # 添加WAD文件路径信息
            GameDataUpdater._add_wad_paths(result["champions"][champ_id], champion["alias"])

            # 处理英雄详细信息
            GameDataUpdater._process_champion_detail(result, champ_id, champion, default_path)

    @staticmethod
    def _add_wad_paths(champion_data: dict, alias: str) -> None:
        """
        添加英雄的WAD文件路径信息

        :param champion_data: 英雄数据
        :param alias: 英雄别名
        """
        # 基础WAD文件路径
        root_wad_path = f"Game/DATA/FINAL/Champions/{alias}.wad.client"

        # 初始化wad字段
        champion_data["wad"] = {"root": root_wad_path}

        # 注意：这里不检查文件是否存在，因为这是一个静态方法，
        # 真正的文件检查会在调用方执行

    @staticmethod
    def _process_champion_detail(result: dict, champ_id: str, champion: dict, champion_path: Path) -> None:
        """
        处理单个英雄的详细信息

        :param result: 结果数据结构
        :param champ_id: 英雄ID
        :param champion: 英雄基本数据
        :param champion_path: 英雄详情文件路径
        """
        detail_file = champion_path / f"{champion['id']}.json"
        if not detail_file.exists():
            return

        try:
            with open(detail_file, encoding="utf-8") as f:
                champion_detail = json.load(f)

            # 添加title字段
            if "title" in champion_detail:
                result["champions"][champ_id]["titles"] = {"default": champion_detail["title"]}

            # 添加皮肤信息
            if "skins" in champion_detail:
                result["champions"][champ_id]["skins"] = GameDataUpdater._process_champion_skins(
                    champion_detail["skins"]
                )

        except Exception as e:
            logger.error(f"处理英雄 {champion['id']} default语言详细信息失败: {str(e)}")

    @staticmethod
    def _process_champion_skins(skins: list) -> list:
        """
        处理英雄的皮肤信息

        :param skins: 皮肤数据列表
        :return: 处理后的皮肤数据列表
        """
        processed_skins = []

        for skin in skins:
            skin_data = {
                "id": skin["id"],
                "isBase": skin.get("isBase", False),
                # "contentId": skin.get("contentId", ""),
                "skinNames": {"default": skin["name"]},
                "audio_data": {},  # 添加音频路径字段，初始为空列表
            }

            # 处理炫彩皮肤
            if "chromas" in skin:
                skin_data["chromas"] = []
                for chroma in skin["chromas"]:
                    chroma_data = {
                        "id": chroma["id"],
                        "chromaNames": {"default": chroma.get("name", "")},
                        "audio_data": {},  # 也为炫彩皮肤添加音频路径字段
                    }
                    skin_data["chromas"].append(chroma_data)

            processed_skins.append(skin_data)

        return processed_skins

    @staticmethod
    def _process_other_language_data(
        result: dict, champions: list, field_availability: dict[str, set], base_path: Path, language: str
    ) -> None:
        """
        处理其他语言的数据

        :param result: 结果数据结构
        :param champions: 该语言的英雄数据
        :param field_availability: 字段可用性信息
        :param base_path: 基础路径
        :param language: 语言代码
        """
        # 检查该语言是否有description字段
        lang_has_description = "description" in field_availability.get(language, set())

        # 检查default语言是否有description字段
        has_description = "description" in field_availability.get("default", set())

        # 遍历该语言的英雄概要
        for champion in champions:
            if champion["id"] == -1:
                continue

            champ_id = str(champion["id"])
            if champ_id not in result["champions"]:
                logger.warning(f"在 {language} 语言中发现default中不存在的英雄ID: {champ_id}，跳过")
                continue

            # 添加该语言的名称
            result["champions"][champ_id]["names"][language] = champion["name"]

            # 仅在该语言有description字段且总体有这个字段时添加description
            if has_description and lang_has_description and "description" in champion:
                if "descriptions" not in result["champions"][champ_id]:
                    result["champions"][champ_id]["descriptions"] = {}
                result["champions"][champ_id]["descriptions"][language] = champion["description"]

            # 处理该语言的英雄详细信息
            GameDataUpdater._process_other_language_champion_detail(result, champ_id, champion, base_path, language)

    @staticmethod
    def _process_other_language_champion_detail(
        result: dict, champ_id: str, champion: dict, base_path: Path, language: str
    ) -> None:
        """
        处理其他语言的英雄详细信息

        :param result: 结果数据结构
        :param champ_id: 英雄ID
        :param champion: 英雄基本数据
        :param base_path: 基础路径
        :param language: 语言代码
        """
        detail_file = base_path / language / "champions" / f"{champion['id']}.json"
        if not detail_file.exists():
            return

        try:
            with open(detail_file, encoding="utf-8") as f:
                champion_detail = json.load(f)

            # 添加title字段
            if "title" in champion_detail:
                if "titles" not in result["champions"][champ_id]:
                    result["champions"][champ_id]["titles"] = {}
                result["champions"][champ_id]["titles"][language] = champion_detail["title"]

            # 处理皮肤名称翻译
            if "skins" in champion_detail and "skins" in result["champions"][champ_id]:
                GameDataUpdater._process_other_language_skins(
                    result["champions"][champ_id]["skins"], champion_detail["skins"], language
                )

        except Exception as e:
            logger.error(f"处理英雄 {champion['id']} {language}语言详细信息失败: {str(e)}")

    @staticmethod
    def _process_other_language_skins(base_skins: list, lang_skins: list, language: str) -> None:
        """
        处理其他语言的皮肤信息

        :param base_skins: 基础皮肤数据
        :param lang_skins: 当前语言的皮肤数据
        :param language: 语言代码
        """
        for i, skin in enumerate(lang_skins):
            if i >= len(base_skins):
                break

            # 添加皮肤名称
            if "name" in skin:
                base_skins[i]["skinNames"][language] = skin["name"]

            # 处理炫彩皮肤名称
            if "chromas" in skin and "chromas" in base_skins[i]:
                for j, chroma in enumerate(skin["chromas"]):
                    if j < len(base_skins[i]["chromas"]):
                        base_skins[i]["chromas"][j]["chromaNames"][language] = chroma.get("name", "")

    @staticmethod
    def _create_indices(result: dict) -> None:
        """
        创建数据索引

        :param result: 结果数据结构
        """
        logger.info("正在创建索引...")

        # 按别名创建索引
        result["indices"]["alias"] = {}
        for champ_id, champion in result["champions"].items():
            alias = champion.get("alias", "").lower()
            if alias:
                result["indices"]["alias"][alias] = champ_id

        logger.info(f"索引创建完成: {len(result['indices']['alias'])} 个别名索引")

    @staticmethod
    def _finalize_result(result: dict, languages: list[str]) -> dict:
        """
        完成结果，添加统计信息并整理结构

        :param result: 结果数据结构
        :param languages: 语言列表
        :return: 最终的结果数据
        """
        # 添加WAD语言文件路径
        GameDataUpdater._add_language_wad_paths(result, languages)

        # 添加统计信息日志
        champion_count = len(result["champions"])
        languages_found = set()
        skin_count = 0

        # 收集统计数据
        for champ in result["champions"].values():
            languages_found.update(champ.get("names", {}).keys())
            skin_count += len(champ.get("skins", []))

        # 创建索引
        GameDataUpdater._create_indices(result)

        # 添加语言信息（不包括默认的en_us/default）
        supported_languages = [lang for lang in languages_found if lang != "default" and lang.lower() != "en_us"]

        # 重新构建结果，确保顺序正确
        final_result = {
            "indices": result["indices"],
            "champions": result["champions"],
            "gameVersion": result["gameVersion"],
            "languages": supported_languages,
            "lastUpdate": result["lastUpdate"],
        }

        logger.info(f"合并完成: {champion_count} 个英雄, {skin_count} 个皮肤, 语言: {supported_languages}")

        return final_result

    @staticmethod
    def _add_language_wad_paths(result: dict, languages: list[str]) -> None:
        """
        为每个英雄添加各语言的WAD文件路径

        :param result: 结果数据结构
        :param languages: 语言列表
        """
        for lang in languages:
            if lang == "default" or lang.lower() == "en_us":
                continue  # 跳过default语言

            for champion_id, champion_data in result["champions"].items():
                alias = champion_data.get("alias", "")
                if not alias:
                    continue

                # 添加该语言的WAD文件路径
                lang_wad_path = f"Game/DATA/FINAL/Champions/{alias}.{lang}.wad.client"
                champion_data["wad"][lang] = lang_wad_path

    @staticmethod
    def _verify_wad_paths(game_path: StrPath, out_dir: StrPath, version: str) -> None:
        """
        验证WAD文件路径是否存在，不存在则记录错误但保持路径信息

        :param game_path: 游戏路径
        :param out_dir: 输出目录
        :param version: 游戏版本
        """
        game_path = Path(game_path)
        merged_file = Path(out_dir) / version / "merged_data.json"

        if not merged_file.exists():
            logger.error(f"合并数据文件不存在: {merged_file}")
            return

        try:
            with open(merged_file, encoding="utf-8") as f:
                data = json.load(f)

            # 遍历所有英雄
            for champion_id, champion_data in data.get("champions", {}).items():
                if "wad" not in champion_data:
                    continue

                # 检查root WAD路径
                root_wad = champion_data["wad"].get("root")
                if root_wad:
                    full_path = game_path / root_wad
                    if not full_path.exists():
                        logger.error(f"英雄 {champion_data.get('alias', champion_id)} 的根WAD文件不存在: {full_path}")

                # 检查语言WAD路径
                for lang, lang_wad in champion_data["wad"].items():
                    if lang != "root":
                        full_path = game_path / lang_wad
                        if not full_path.exists():
                            logger.error(
                                f"英雄 {champion_data.get('alias', champion_id)} 的 {lang} 语言WAD文件不存在: {full_path}"
                            )

            # 保存更新后的数据
            with open(merged_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)

        except Exception as e:
            logger.error(f"验证WAD路径时出错: {str(e)}")
            logger.debug(traceback.format_exc())


class GameDataReader(metaclass=Singleton):
    """
    从合并后的数据文件读取游戏数据
    """

    def __init__(self, data_file: StrPath, default_language: str = "default"):
        """
        初始化数据读取器

        :param data_file: 合并后的JSON数据文件路径
        :param default_language: 默认使用的语言
        """
        # 防止单例被重复初始化
        if hasattr(self, "initialized"):
            return

        self.default_language = default_language
        self.data = self._load_data(data_file)
        self.version = self.data.get("gameVersion", "unknown")
        self.initialized = True

    def _load_data(self, data_file: StrPath) -> dict:
        """
        加载数据文件

        :param data_file: JSON数据文件路径
        :return: 加载的数据
        """
        try:
            with open(data_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载数据文件时出错: {str(e)}")
            return {"champions": {}, "gameVersion": "unknown"}

    def set_language(self, language: str) -> None:
        """
        设置默认语言

        :param language: 语言代码
        """
        self.default_language = language

    def get_supported_languages(self) -> list[str]:
        """
        获取支持的语言列表

        :return: 语言代码列表
        """
        # 从英雄数据中获取所有语言
        languages = set()
        for champion in self.data.get("champions", {}).values():
            languages.update(champion.get("names", {}).keys())
        return list(languages)

    def get_champion_by_id(self, champion_id: int, language: str = None) -> dict:
        """
        根据ID获取英雄信息

        :param champion_id: 英雄ID
        :param language: 语言代码，不使用，保留参数仅为兼容性
        :return: 英雄信息
        """
        champ_id = str(champion_id)

        champion = self.data.get("champions", {}).get(champ_id)
        if not champion:
            return {}

        # 直接返回原始数据，不做任何转换处理
        return champion

    def get_champion_by_alias(self, alias: str, language: str = None) -> dict:
        """
        根据别名获取英雄信息

        :param alias: 英雄别名
        :param language: 语言代码，不使用，保留参数仅为兼容性
        :return: 英雄信息
        """
        # 使用索引查找
        if "indices" in self.data and "alias" in self.data.get("indices", {}):
            champ_id = self.data["indices"]["alias"].get(alias.lower())
            if champ_id:
                return self.data.get("champions", {}).get(champ_id, {})

        # 索引不存在或未找到，回退到传统查找方式
        for champion_id, champion in self.data.get("champions", {}).items():
            if champion["alias"].lower() == alias.lower():
                return champion
        return {}

    def get_champions_list(self, language: str = None) -> list[dict]:
        """
        获取所有英雄列表

        :param language: 语言代码，不使用，保留参数仅为兼容性
        :return: 英雄列表
        """
        return list(self.data.get("champions", {}).values())


if __name__ == "__main__":
    logger.disable("league_tools")
    g = GameDataUpdater.check_and_update(
        r"D:\Games\Tencent\WeGameApps\英雄联盟", r"E:\Temp\Scratch\lol", languages=["zh_CN", "ja_JP", "ko_KR"]
    )
