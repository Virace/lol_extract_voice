# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2022/8/15 23:56
# @Update  : 2024/9/8 19:30
# @Detail  : 游戏数据

import json
import re
import traceback
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union

import requests
from league_tools.formats import WAD
from loguru import logger
from riotmanifest import ResourceDL, RiotGameData, WADExtractor

from lol_audio_unpack.Utils.common import format_region
from lol_audio_unpack.Utils.type_hints import StrPath


class GameData:
    """
    获取游戏相关数据
    """

    def __init__(
        self,
        out_dir: StrPath,
        mode: str = "local",
        game_path: Optional[StrPath] = None,
        temp_path: Optional[StrPath] = None,
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

        self.rdl: Optional[ResourceDL] = None
        self.rgd: Optional[RiotGameData] = None
        self.lcu_extractor: Optional[WADExtractor] = None
        self.game_extractor: Optional[WADExtractor] = None

        if self.mode == "local":
            if game_path is None:
                raise ValueError("local 模式不可缺少 game_path")
            self.game_path = Path(game_path)

        elif self.mode == "remote":
            if temp_path is None:
                raise ValueError("remote 模式不可缺少 temp_path")
            self.remote_path = Path(temp_path) / "remote"
            self.game_path = self.remote_path
            self._remote_initialize()
        else:
            raise ValueError("错误的模式. 只接受local、remote")

        self.out_dir = Path(out_dir) / self.get_game_version()

        if self.mode in ["remote"]:
            self.rdl = ResourceDL(self.game_path)

        if self.region.lower() == "en_us":
            self.region = "default"

        self._version_api = "https://ddragon.leagueoflegends.com/api/versions.json"

        # 游戏英雄文件目录 (Game/DATA/FINAL/Champions)
        self.GAME_CHAMPION_PATH = self.game_path / "Game" / "DATA" / "FINAL" / "Champions"

        # 游戏地图(公共)文件目录 (Game/DATA/FINAL/Maps/Shipping)
        self.GAME_MAPS_PATH = self.game_path / "Game" / "DATA" / "FINAL" / "Maps" / "Shipping"

        self.rgd = RiotGameData()
        self.rgd.load_lcu_data()
        self.rgd.load_game_data()
        self.lcu_extractor = WADExtractor(self.rgd.lastest_lcu().url)
        self.game_extractor = WADExtractor(self.rgd.latest_game().url)

    def _remote_initialize(self):
        """
        创建各种对象，并且根据正则下载文件，
        :return:
        """
        logger.debug("remote模式，开始下载所需文件.")
        self.rdl = ResourceDL(self.game_path)
        self.rdl.d_game = True
        self.rdl.d_lcu = True
        self.rdl.download_resources(
            r"DATA/FINAL/Champions/\w+.zh_CN.wad.client|content-metadata.json",
            rf"Plugins/rcp-be-lol-game-data/{self.region}-assets.wad",
        )

    @staticmethod
    def to_relative_path(path: StrPath) -> Optional[StrPath]:
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
        return file_path[match.start() + 1 :]

    def _get_out_path(self, files: Union[str, List[str]] = "") -> Path:
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

    def _open_file(self, filename: Union[str, List[str]]) -> Dict:
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

    def get_summary(self) -> Dict:
        """
        获取英雄列表
        :return:
        """
        return self._open_file("champion-summary.json")

    def get_skins(self) -> Dict:
        """
        获取皮肤列表
        :return:
        """
        return self._open_file("skins.json")

    def get_skinlines(self) -> Dict:
        """
        获取皮肤系列列表
        :return:
        """
        temp = self._open_file("skinlines.json")
        result = {item["id"]: item["name"] for item in temp}
        return result

    def get_maps(self) -> Dict:
        """
        获取地图列表
        :return:
        """
        return self._open_file("maps.json")

    def get_champion_detail_by_id(self, cid: int) -> Dict:
        """
        根据英雄ID获取英雄详情
        :param cid:
        :return:
        """
        return self._open_file(["champions", f"{cid}.json"])

    def get_champion_name(self, name: str, chinese: bool = True) -> Optional[Union[str, tuple]]:
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

    def get_champions_name(self) -> Dict[str, str]:
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

    def get_champions_alias(self) -> Dict[str, str]:
        """
        获取英雄代号, 说是代号，其实json中是name
        :return:
        """
        return {item["alias"].lower(): item["name"] for item in self.get_summary()}

    def get_champions_id(self) -> List[int]:
        """
        获取英雄ID
        :return:
        """
        return [item["id"] for item in self.get_summary()]

    def get_maps_id(self) -> List[int]:
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

        wad_file = (
            self.game_path
            / "LeagueClient"
            / "Plugins"
            / "rcp-be-lol-game-data"
            / f"{format_region(self.region)}-assets.wad"
        )

        hash_table = [
            f"plugins/rcp-be-lol-game-data/global/{self.region}/v1/champion-summary.json",
            f"plugins/rcp-be-lol-game-data/global/{self.region}/v1/skinlines.json",
            f"plugins/rcp-be-lol-game-data/global/{self.region}/v1/skins.json",
            f"plugins/rcp-be-lol-game-data/global/{self.region}/v1/maps.json",
            f"plugins/rcp-be-lol-game-data/global/{self.region}/v1/items.json",
            f"plugins/rcp-be-lol-game-data/global/{self.region}/v1/universes.json",
        ]
        self.wad_extract(wad_file, hash_table, output_file_name)
        self.wad_extract(
            wad_file,
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

                _hash_list.append(f'{_head}/v1/champion-splashes/{cid}/{item["id"]}.jpg')
                _hash_list.append(f'{_head}/v1/champion-splashes/uncentered/{cid}/{item["id"]}.jpg')
                _hash_list.append(f'{_head}/v1/champion-tiles/{cid}/{item["id"]}.jpg')
                _hash_list.append(fix_hash_path(item["loadScreenPath"]))

                # 炫彩
                if "chromas" in item:
                    _hash_list.append(f'{_head}/v1/chromaPath/{cid}/{item["id"]}.jpg')
                    for chroma in item["chromas"]:
                        _hash_list.append(f'{_head}/v1/champion-chroma-images/{cid}/{item["id"]}/{chroma["id"]}.jpg')

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
        hash_table: List[str],
        out_dir: Optional[Union[StrPath, Callable[[StrPath], StrPath]]] = None,
        raw: bool = False,
    ) -> Optional[List[bytes]]:
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

        file_path = self.to_relative_path(wad_file)

        # 根据路径前缀选择合适的 WADExtractor
        wad_extractor = None
        if file_path.startswith("DATA"):
            wad_extractor = self.game_extractor
        elif file_path.startswith("Plugins"):
            wad_extractor = self.lcu_extractor

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
