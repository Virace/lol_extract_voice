# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2022/8/15 23:56
# @Update  : 2024/5/4 19:45
# @Detail  : 游戏数据

import json
import re
import traceback
from pathlib import Path

import requests
from loguru import logger
from league_tools.formats import WAD

from Utils.common import format_region
from Utils.type_hints import StrPath


class GameData:
    """
    获取游戏相关数据
    """

    def __init__(
        self, game_path: StrPath, manifest_path: StrPath, region: str = "zh_CN"
    ):
        """
        :param region: 地区
        """
        self.game_path = Path(game_path)
        self.out_path = Path(manifest_path)
        self.region = region
        if self.region.lower() == "en_us":
            self.region = "default"
        self.data_path = (
            self.game_path / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data"
        )
        self.wad_file_region = (
            self.data_path / f"{format_region(self.region)}-assets.wad"
        )
        self.wad_file_default = self.data_path / "default-assets.wad"

        self._version_api = "https://ddragon.leagueoflegends.com/api/versions.json"

        # 游戏英雄文件目录 (Game/DATA/FINAL/Champions)
        self.GAME_CHAMPION_PATH = (
            self.game_path / "Game" / "DATA" / "FINAL" / "Champions"
        )

        # 游戏地图(公共)文件目录 (Game/DATA/FINAL/Maps/Shipping)
        self.GAME_MAPS_PATH = (
            self.game_path / "Game" / "DATA" / "FINAL" / "Maps" / "Shipping"
        )

    def _get_out_path(self, files: [str, list[str]] = ""):
        """
        获取输出路径
        :param files: 文件, 可传入数组 则为多级目录
        :return: 完整的文件路径
        """
        if isinstance(files, str):
            files = [files]
        elif not isinstance(files, list):
            raise TypeError("files 必须是字符串或字符串列表")
        return (self.out_path / self.region).joinpath(*files)

    def _open_file(self, filename: [str, list[str]]) -> dict:
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
        except IOError:
            logger.warning(f"无法读取文件 {file}")
        except Exception as e:
            logger.warning(f"打开文件 {file} 时发生未知错误: {str(e)}")
            logger.debug(traceback.format_exc())
        return {}

    def get_summary(
        self,
    ):
        """
        获取英雄列表
        :return:
        """
        return self._open_file("champion-summary.json")

    def get_skins(
        self,
    ):
        """
        获取皮肤列表
        :return:
        """
        return self._open_file("skins.json")

    def get_skinlines(
        self,
    ):
        """
        获取皮肤系列列表
        :return:
        """
        temp = self._open_file("skinlines.json")
        result = {item["id"]: item["name"] for item in temp}
        return result

    def get_maps(
        self,
    ):
        """
        获取地图列表
        :return:
        """
        return self._open_file("maps.json")

    def get_champion_detail_by_id(
        self,
        cid,
    ):
        """
        根据英雄ID获取英雄详情
        :param cid:
        :return:
        """
        return self._open_file(["champions", f"{cid}.json"])

    def get_champion_name(self, name, chinese=True):
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

    def get_champions_name(
        self,
    ):
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

    def get_champions_alias(
        self,
    ):
        """
        获取英雄代号, 说是代号，其实json中是name
        :return:
        """
        return {item["alias"].lower(): item["name"] for item in self.get_summary()}

    def get_champions_id(
        self,
    ):
        """
        获取英雄ID
        :return:
        """
        return [item["id"] for item in self.get_summary()]

    def get_maps_id(
        self,
    ):
        """
        获取地图ID
        :return:
        """
        return [item["id"] for item in self.get_maps()]

    def get_manifest(self):
        """
        获取文件清单
        :return:
        """
        logger.trace("获取文件清单")
        if self.region == "en_us":
            region = "default"

        def output_file_name(path: str):
            old = f"plugins/rcp-be-lol-game-data/global/{region}/v1/"
            new = path.replace(old, "")
            return self._get_out_path() / Path(new)

        hash_table = [
            f"plugins/rcp-be-lol-game-data/global/{self.region}/v1/champion-summary.json",
            f"plugins/rcp-be-lol-game-data/global/{self.region}/v1/skinlines.json",
            f"plugins/rcp-be-lol-game-data/global/{self.region}/v1/skins.json",
            f"plugins/rcp-be-lol-game-data/global/{self.region}/v1/maps.json",
            f"plugins/rcp-be-lol-game-data/global/{self.region}/v1/items.json",
            f"plugins/rcp-be-lol-game-data/global/{self.region}/v1/universes.json",
        ]
        WAD(self.wad_file_region).extract(hash_table, out_dir=output_file_name)
        WAD(self.wad_file_region).extract(
            [
                f"plugins/rcp-be-lol-game-data/global/{self.region}/v1/champions/"
                f'{item["id"]}.json'
                for item in self.get_summary()
            ],
            out_dir=output_file_name,
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

            return self.out_path / "images" / Path(new)

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

                _hash_list.append(
                    f'{_head}/v1/champion-splashes/{cid}/{item["id"]}.jpg'
                )
                _hash_list.append(
                    f'{_head}/v1/champion-splashes/uncentered/{cid}/{item["id"]}.jpg'
                )
                _hash_list.append(f'{_head}/v1/champion-tiles/{cid}/{item["id"]}.jpg')
                _hash_list.append(fix_hash_path(item["loadScreenPath"]))

                # 炫彩
                if "chromas" in item:
                    _hash_list.append(f'{_head}/v1/chromaPath/{cid}/{item["id"]}.jpg')
                    for chroma in item["chromas"]:
                        _hash_list.append(
                            f'{_head}/v1/champion-chroma-images/{cid}/{item["id"]}/{chroma["id"]}.jpg'
                        )
        WAD(self.wad_file_default).extract(_hash_list, out_dir=output_file_name)

    def get_game_version(self, default="99.99"):
        """
        获取游戏版本
        :param default:
        :return:
        """
        meta = self.game_path / "Game" / "content-metadata.json"
        if meta.exists():
            with open(meta, encoding="utf-8") as f:
                data = json.load(f)
            version_v = data["version"]
        else:
            return default
        if m := re.match(r"^(\d+\.\d+)\.", version_v):
            return m.group(1)

    def get_latest_version(self):
        """
        获取最新版本
        :return:
        """
        return requests.get(self._version_api).json()[0]

    def update_data(self):
        """
        根据本地游戏文件获取 数据文件
        :return:
        """
        _region = self.region
        # 游戏内英文文件作为default默认存在
        if self.region == "en_us":
            _region = "default"

        def output_file_name(path):
            old = f"plugins/rcp-be-lol-game-data/global/{_region}/v1/"
            new = path.replace(old, "")
            return self.out_path / _region / Path(new)

        data_path = self.game_path / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data"

        wad_file = data_path / f"{format_region(_region)}-assets.wad"
        hash_table = [
            f"plugins/rcp-be-lol-game-data/global/{_region}/v1/champion-summary.json",
            f"plugins/rcp-be-lol-game-data/global/{_region}/v1/skinlines.json",
            f"plugins/rcp-be-lol-game-data/global/{_region}/v1/skins.json",
            f"plugins/rcp-be-lol-game-data/global/{_region}/v1/maps.json",
            f"plugins/rcp-be-lol-game-data/global/{_region}/v1/items.json",
            f"plugins/rcp-be-lol-game-data/global/{_region}/v1/universes.json",
        ]
        WAD(wad_file).extract(hash_table, out_dir=output_file_name)
        WAD(wad_file).extract(
            [
                f'plugins/rcp-be-lol-game-data/global/{_region}/v1/champions/{item["id"]}.json'
                for item in self.get_summary()
            ],
            out_dir=output_file_name,
        )


def compare_version(version1: str, version2: str) -> None:
    """
    比较版本号, # todo: 这玩意没实测， 有问题再说
    :param version1:
    :param version2:
    :return:
    """
    # 检查输入格式
    if not is_valid_version(version1) or not is_valid_version(version2):
        logger.error(
            "版本号格式不正确，请使用 '大版本.小版本' 或 '大版本.小版本.修订号' 格式。"
        )
        return

    version1_parts = version1.split(".")
    version2_parts = version2.split(".")

    major_version1, minor_version1 = int(version1_parts[0]), int(version1_parts[1])
    major_version2, minor_version2 = int(version2_parts[0]), int(version2_parts[1])

    if major_version1 != major_version2:
        raise ValueError(
            f"大版本不同，无法比较。版本号分别为: {version1} 和 {version2}"
        )
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
