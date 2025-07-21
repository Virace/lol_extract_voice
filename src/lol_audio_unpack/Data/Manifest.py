# 🐍 There should be one-- and preferably only one --obvious way to do it.
# 🐼 任何问题应有一种，且最好只有一种，显而易见的解决方法
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2022/8/15 23:56
# @Update  : 2025/7/22 6:33
# @Detail  : 游戏数据


import json
import re
import shutil
import tempfile
import traceback
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import requests
from league_tools.formats import WAD
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
                with open(merged_file, "r", encoding="utf-8") as f:
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
        # 调整初始化顺序，但实际输出顺序会根据添加顺序决定
        result = {
            "indices": {},  # 先预留索引位置
            "champions": {},
            "gameVersion": version,
            "lastUpdate": datetime.now().isoformat(),
        }

        # 确保default在语言列表中
        if "default" not in languages:
            logger.error("语言列表必须包含'default'")
            return

        # 第一步：读取所有语言的champion-summary.json
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

        # 如果没有找到default语言的数据，无法继续
        if "default" not in champion_summaries:
            logger.error("未找到default语言的英雄概要数据，无法处理")
            return

        # 检查各个语言文件的字段情况
        field_availability = {}
        for lang, champions in champion_summaries.items():
            # 用第一个英雄作为检查样本
            if champions and len(champions) > 0:
                sample_champion = champions[0]
                fields = set(sample_champion.keys())
                field_availability[lang] = fields
                logger.debug(f"{lang} 语言的champion字段: {fields}")

        # 第二步：基于default语言构建基本结构
        default_champions = champion_summaries["default"]
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

            # 处理英雄详细信息（基于default语言）
            detail_file = default_path / f"{champion['id']}.json"
            if detail_file.exists():
                try:
                    with open(detail_file, encoding="utf-8") as f:
                        champion_detail = json.load(f)

                    # 添加title字段
                    if "title" in champion_detail:
                        result["champions"][champ_id]["titles"] = {"default": champion_detail["title"]}

                    # 添加皮肤信息
                    if "skins" in champion_detail:
                        processed_skins = []
                        for skin in champion_detail["skins"]:
                            skin_data = {
                                "id": skin["id"],
                                "isBase": skin.get("isBase", False),
                                # "contentId": skin.get("contentId", ""),
                                "skinNames": {"default": skin["name"]},
                            }

                            # 处理炫彩皮肤
                            if "chromas" in skin:
                                skin_data["chromas"] = []
                                for chroma in skin["chromas"]:
                                    chroma_data = {
                                        "id": chroma["id"],
                                        "chromaNames": {"default": chroma.get("name", "")},
                                    }
                                    skin_data["chromas"].append(chroma_data)

                            processed_skins.append(skin_data)

                        result["champions"][champ_id]["skins"] = processed_skins
                except Exception as e:
                    logger.error(f"处理英雄 {champion['id']} default语言详细信息失败: {str(e)}")

        # 第三步：添加其他语言的数据
        for language in languages:
            if language == "default" or language.lower() == "en_us":
                continue  # 已经处理过default语言

            if language not in champion_summaries:
                continue  # 没有该语言的数据

            # 检查该语言是否有description字段
            lang_has_description = "description" in field_availability.get(language, set())

            # 遍历该语言的英雄概要
            for champion in champion_summaries[language]:
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
                detail_file = base_path / language / "champions" / f"{champion['id']}.json"
                if detail_file.exists():
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
                            for i, skin in enumerate(champion_detail["skins"]):
                                if i < len(result["champions"][champ_id]["skins"]):
                                    # 添加皮肤名称
                                    if "name" in skin:
                                        result["champions"][champ_id]["skins"][i]["skinNames"][language] = skin["name"]

                                    # 处理炫彩皮肤名称
                                    if "chromas" in skin and "chromas" in result["champions"][champ_id]["skins"][i]:
                                        for j, chroma in enumerate(skin["chromas"]):
                                            if j < len(result["champions"][champ_id]["skins"][i]["chromas"]):
                                                result["champions"][champ_id]["skins"][i]["chromas"][j]["chromaNames"][
                                                    language
                                                ] = chroma.get("name", "")
                    except Exception as e:
                        logger.error(f"处理英雄 {champion['id']} {language}语言详细信息失败: {str(e)}")

        # 添加统计信息日志
        champion_count = len(result["champions"])
        languages_found = set()
        skin_count = 0

        # 收集统计数据
        for champ in result["champions"].values():
            languages_found.update(champ.get("names", {}).keys())
            skin_count += len(champ.get("skins", []))

        # 创建索引
        logger.info("正在创建索引...")

        # 按别名创建索引
        result["indices"]["alias"] = {}
        for champ_id, champion in result["champions"].items():
            alias = champion.get("alias", "").lower()
            if alias:
                result["indices"]["alias"][alias] = champ_id

        logger.info(f"索引创建完成: {len(result['indices']['alias'])} 个别名索引")

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

        # 保存合并后的数据
        merged_file = base_path / "merged_data.json"
        with open(merged_file, "w", encoding="utf-8") as f:
            json.dump(final_result, f, ensure_ascii=False)


class GameData:
    """
    获取游戏相关数据
    """

    def __init__(
            self,
            out_dir: StrPath,
            mode: str = "local",
            game_path: StrPath | None = None,
            temp_path: StrPath | None = None,
            region: str = "zh_CN",
    ):
        """
        初始化 GameData 类。

        :param out_dir: 清单文件的存储路径，所有模式都需要。
        :param mode: 运行模式，可以是 'local'、'remote'。
        :param game_path: 游戏的本地路径，仅在 local 模式下需要。
        :param temp_path: 临时文件的存储路径，仅在 remote 模式下需要。
        :param region: 地区代码，默认为 "zh_CN"。
        :raises ValueError: 如果模式不正确或者缺少必要路径。
        """
        self.mode = mode
        self.region = region
        self.game_path = None
        self.remote_path = None

        if self.mode == "local":
            if game_path is None:
                raise ValueError("local 模式不可缺少 game_path")
            self.game_path = Path(game_path)

        elif self.mode == "remote":
            if temp_path is None:
                raise ValueError("remote 模式不可缺少 temp_path")
            self.remote_path = Path(temp_path) / "remote"
            self.game_path = self.remote_path
            # self._remote_initialize()
        else:
            raise ValueError("错误的模式. 只接受local、remote")

        self.out_dir = Path(out_dir) / self.get_game_version()

        if self.region.lower() == "en_us":
            self.region = "default"

        self._version_api = "https://ddragon.leagueoflegends.com/api/versions.json"

        # 游戏英雄文件目录 (Game/DATA/FINAL/Champions)
        self.GAME_CHAMPION_PATH = self.game_path / "Game" / "DATA" / "FINAL" / "Champions"

        # 游戏地图(公共)文件目录 (Game/DATA/FINAL/Maps/Shipping)
        self.GAME_MAPS_PATH = self.game_path / "Game" / "DATA" / "FINAL" / "Maps" / "Shipping"

    @staticmethod
    def to_relative_path(path: StrPath) -> StrPath | None:
        """
        将本地路径转换为 清单中相对路径
        :param path:
        :return:
        """

        path = Path(path)

        # 将路径标准化为 POSIX 格式
        file_path = path.as_posix()
        # 匹配路径中的关键字
        match = re.search(r"/(DATA|Plugins)/", file_path, re.IGNORECASE)
        if not match:
            return None

        # 提取从匹配模式开始的路径部分
        return file_path[match.start() + 1:]

    def _get_out_path(self, files: str | list[str] = "") -> Path:
        """
        获取输出路径
        :param files: 文件, 可传入数组 则为多级目录
        :return: 完整的文件路径
        """
        if isinstance(files, str):
            files = [files]
        elif not isinstance(files, list):
            raise TypeError("files 必须是字符串或字符串列表")
        return (self.out_dir / self.region).joinpath(*files)

    def _open_file(self, filename: str | list[str]) -> dict:
        """
        打开并读取 JSON 文件
        :param filename: 文件名
        :return: 文件内容
        """
        file = self._get_out_path(filename)
        try:
            with open(file, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"文件 {file} 不存在")
        except json.JSONDecodeError:
            logger.warning(f"无法解析文件 {file}，文件可能不是有效的 JSON 格式")
        except OSError:
            logger.warning(f"无法读取文件 {file}")
        except Exception as e:
            logger.warning(f"打开文件 {file} 时发生未知错误: {str(e)}")
            logger.debug(traceback.format_exc())
        return {}

    def get_summary(self) -> dict:
        """
        获取英雄列表
        :return:
        """
        return self._open_file("champion-summary.json")

    def get_skins(self) -> dict:
        """
        获取皮肤列表
        :return:
        """
        return self._open_file("skins.json")

    def get_skinlines(self) -> dict:
        """
        获取皮肤系列列表
        :return:
        """
        temp = self._open_file("skinlines.json")
        result = {item["id"]: item["name"] for item in temp}
        return result

    def get_maps(self) -> dict:
        """
        获取地图列表
        :return:
        """
        return self._open_file("maps.json")

    def get_champion_detail_by_id(self, cid: int) -> dict:
        """
        根据英雄ID获取英雄详情
        :param cid:
        :return:
        """
        return self._open_file(["champions", f"{cid}.json"])

    def get_champion_name(self, name: str, chinese: bool = True) -> str | tuple | None:
        """
        根据游戏数据获取中文名称
        :param name:
        :param chinese:
        :return:
        """
        summary = self.get_summary()
        for item in summary:
            if item["alias"].lower() == name.lower():
                if chinese:
                    return item["alias"], item["name"]
                else:
                    return item["alias"]

    def get_champions_name(self) -> dict[str, str]:
        """
        获取英雄名字, 说是名字, 其实json中是title
        :return:
        """
        res = {}
        summary = self.get_summary()
        for item in summary:
            if item["id"] == -1:
                continue

            this = self.get_champion_detail_by_id(item["id"])
            res[item["alias"]] = this["title"]
        return res

    def get_champions_alias(self) -> dict[str, str]:
        """
        获取英雄代号, 说是代号，其实json中是name
        :return:
        """
        return {item["alias"].lower(): item["name"] for item in self.get_summary()}

    def get_champions_id(self) -> list[int]:
        """
        获取英雄ID
        :return:
        """
        return [item["id"] for item in self.get_summary()]

    def get_maps_id(self) -> list[int]:
        """
        获取地图ID
        :return:
        """
        return [item["id"] for item in self.get_maps()]

    def get_data(self):
        """
        获取文件清单
        :return:
        """
        logger.trace("获取文件清单")

        def output_file_name(path: str):
            reg = re.compile(rf"plugins/rcp-be-lol-game-data/global/{self.region}/v1/", re.IGNORECASE)
            new = reg.sub("", path)
            return self._get_out_path() / Path(new)

        # 前缀
        _head = format_region(self.region)
        # 目录下可能有多个 default-assets开头的文件，例如 default-assets.wad default-assets2.wad 等等
        # 如果_head == 'default'则 wad_file为数组 包含所有default-assets开头的文件
        if _head == "default":
            wad_file = list(self.game_path.glob("LeagueClient/Plugins/rcp-be-lol-game-data/default-assets*.wad"))
        else:
            wad_file = [self.game_path / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data" / f"{_head}-assets.wad"]

        logger.trace(wad_file)

        hash_table = [
            f"plugins/rcp-be-lol-game-data/global/{self.region}/v1/champion-summary.json",
            f"plugins/rcp-be-lol-game-data/global/{self.region}/v1/skinlines.json",
            f"plugins/rcp-be-lol-game-data/global/{self.region}/v1/skins.json",
            f"plugins/rcp-be-lol-game-data/global/{self.region}/v1/maps.json",
            f"plugins/rcp-be-lol-game-data/global/{self.region}/v1/items.json",
            f"plugins/rcp-be-lol-game-data/global/{self.region}/v1/universes.json",
        ]
        for file in wad_file:
            self.wad_extract(file, hash_table, output_file_name)
            self.wad_extract(
                file,
                [
                    rf"plugins/rcp-be-lol-game-data/global/{self.region}/v1/champions/{item['id']}.json"
                    for item in self.get_summary()
                ],
                output_file_name,
            )

    def get_images(self):
        """
        获取英雄有关图片文件(头像、原画等)
        :return:
        """
        _hash_list = []
        _head = "plugins/rcp-be-lol-game-data/global/default"

        def fix_hash_path(path):
            return f"{_head}/{path.replace('/lol-game-data/assets/', '')}"

        def output_file_name(path):
            old = "plugins/rcp-be-lol-game-data/global/default/v1/"
            loading = "plugins/rcp-be-lol-game-data/global/default/ASSETS/Characters"
            new = path.replace(old, "")
            new = new.replace(loading, "champion-loadscreen")

            return self.out_dir / "images" / Path(new)

        champions = self.get_summary()
        for champion in champions:
            cid = champion["id"]

            c_data = self.get_champion_detail_by_id(cid)
            _hash_list.append(fix_hash_path(c_data["squarePortraitPath"]))

            for item in c_data["skins"]:
                # "splashPath": "/lol-game-data/assets/v1/champion-splashes/2/2000.jpg",
                # "uncenteredSplashPath": "/lol-game-data/assets/v1/champion-splashes/uncentered/2/2000.jpg",
                # "tilePath": "/lol-game-data/assets/v1/champion-tiles/2/2000.jpg",
                # "loadScreenPath": "/lol-game-data/assets/ASSETS/Characters/Olaf/Skins/Base/OlafLoadScreen.jpg",

                _hash_list.append(f"{_head}/v1/champion-splashes/{cid}/{item['id']}.jpg")
                _hash_list.append(f"{_head}/v1/champion-splashes/uncentered/{cid}/{item['id']}.jpg")
                _hash_list.append(f"{_head}/v1/champion-tiles/{cid}/{item['id']}.jpg")
                _hash_list.append(fix_hash_path(item["loadScreenPath"]))

                # 炫彩
                if "chromas" in item:
                    _hash_list.append(f"{_head}/v1/chromaPath/{cid}/{item['id']}.jpg")
                    for chroma in item["chromas"]:
                        _hash_list.append(f"{_head}/v1/champion-chroma-images/{cid}/{item['id']}/{chroma['id']}.jpg")

        wad_file = self.game_path / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data" / "default-assets.wad"
        self.wad_extract(wad_file, _hash_list, out_dir=output_file_name)

    def get_game_version(self):
        """
        获取游戏版本
        :return:
        """
        meta = self.game_path / "Game" / "content-metadata.json"
        if not meta.exists():
            raise FileNotFoundError("content-metadata.json 文件不存在无法判断版本信息")

        with open(meta, encoding="utf-8") as f:
            data = json.load(f)

        version_v = data["version"]

        if m := re.match(r"^(\d+\.\d+)\.", version_v):
            return m.group(1)

    def get_latest_version(self) -> str:
        """
        获取最新版本。

        :return: 最新版本号。
        """
        try:
            return requests.get(self._version_api).json()[0]
        except requests.exceptions.RequestException as e:
            logger.warning(f"获取最新版本时发生错误: {str(e)}")
            return ""

    def wad_extract(
            self,
            wad_file: StrPath,
            hash_table: list[str],
            out_dir: StrPath | Callable[[StrPath], StrPath] | None = None,
            raw: bool = False,
    ) -> list[bytes] | None:
        """
        解包 WAD 文件。如果 WAD 文件不存在，则使用 WADExtractor 类从网络获取。

        :param wad_file: WAD 文件的路径
        :param hash_table: 用于解包的哈希表
        :param out_dir: 输出目录
        :param raw: 是否返回原始数据
        :return: 解包后的数据或文件
        """
        wad_file = Path(wad_file)

        if wad_file.exists():
            # 如果文件存在，直接使用本地解包
            return WAD(wad_file).extract(hash_table, "" if out_dir is None else out_dir, raw)
        logger.error(f"文件不存在: {wad_file}")
        return None
        # raise ValueError(f'文件不存在: {wad_file}')
        file_path = self.to_relative_path(wad_file)

        # 根据路径前缀选择合适的 WADExtractor
        wad_extractor = None
        # if file_path.startswith("DATA"):
        #     wad_extractor = self.rgd.game_wad
        # elif file_path.startswith("Plugins"):
        #     wad_extractor = self.rgd.lcu_wad

        if wad_extractor is None:
            return

        # 从网络提取文件
        file_raw = wad_extractor.extract_files({file_path: hash_table})
        if raw:
            temp = file_raw.get(file_path)
            return [temp[item] for item in hash_table]

        # 保存文件到指定目录
        for item, data in file_raw.get(file_path, {}).items():
            if data:
                if callable(out_dir):
                    output_file = out_dir(item)
                else:
                    output_file = Path(out_dir) / item
                output_file.parent.mkdir(parents=True, exist_ok=True)
                with open(output_file, "wb") as f:
                    f.write(data)


def compare_version(version1: str, version2: str) -> None:
    """
    比较版本号, # todo: 这玩意没实测， 有问题再说
    :param version1:
    :param version2:
    :return:
    """
    # 检查输入格式
    if not is_valid_version(version1) or not is_valid_version(version2):
        logger.error("版本号格式不正确，请使用 '大版本.小版本' 或 '大版本.小版本.修订号' 格式。")
        return

    version1_parts = version1.split(".")
    version2_parts = version2.split(".")

    major_version1, minor_version1 = int(version1_parts[0]), int(version1_parts[1])
    major_version2, minor_version2 = int(version2_parts[0]), int(version2_parts[1])

    if major_version1 != major_version2:
        raise ValueError(f"大版本不同，无法比较。版本号分别为: {version1} 和 {version2}")
    elif minor_version1 != minor_version2:
        logger.warning(f"小版本不同，请注意。版本号分别为: {version1} 和 {version2}")

    # logger.info("版本号比较完成。")


def is_valid_version(version: str) -> bool:
    parts = version.split(".")
    if len(parts) < 2 or len(parts) > 3:
        return False
    try:
        major, minor = map(int, parts[:2])
        if major < 0 or minor < 0:
            return False
    except ValueError:
        return False
    return True


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
    g = GameDataUpdater.check_and_update(
        r"D:\Games\Tencent\WeGameApps\英雄联盟", r"E:\Temp\Scratch\lol", languages=["zh_CN", "ja_JP", "ko_KR"]
    )
