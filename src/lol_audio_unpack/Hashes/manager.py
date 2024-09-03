# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2024/3/12 13:20
# @Update  : 2024/9/3 10:24
# @Detail  : 

import gc
import re
import sys
from collections import defaultdict
from pathlib import Path

import league_tools
from league_tools.formats import BIN, WAD, StringHash
from loguru import logger

from lol_audio_unpack.Data.Manifest import GameData
from lol_audio_unpack.Utils.common import EnhancedPath, de_duplication, dump_json, load_json, makedirs, tree, capitalize_first_letter
from lol_audio_unpack.Utils.type_hints import StrPath


class HashManager:
    def __init__(
        self,
        game_path: StrPath,
        manifest_path: StrPath,
        hash_path: StrPath,
        region: str = "zh_CN",
        log_path: StrPath | None = None,
    ):
        """
        哈希表管理器
        :param hash_path:
        :param region:
        :param log_path:
        """
        game_path = Path(game_path)
        manifest_path = Path(manifest_path)
        hash_path = Path(hash_path)
        if log_path:
            log_path = Path(log_path)

        self.game_data = GameData(game_path, manifest_path, region)
        self.game_data_default = GameData(game_path, manifest_path, "en_us")

        self.game_version: str = self.game_data.get_game_version()

        self.workspace = hash_path / self.game_version

        self.event_hash_path = self.workspace / "event"
        self.e2a_hash_path = self.workspace / "event2audio"

        makedirs(self.event_hash_path)
        makedirs(self.e2a_hash_path)

        self.region = region

        self.bin_hash_file = self.workspace / "bin.json"
        self.bnk_hash_file = self.workspace / f"bnk.{self.region}.json"
        self.event_hash_tpl = EnhancedPath(self.event_hash_path / "{kind}" / "{name}.json")
        self.audio_hash_tpl = EnhancedPath(
            self.e2a_hash_path / "{region}" / "{type}" / "{kind}" / "{name}" / "{skin}.json"
        )

        self.integrate_hash_table_file = self.workspace / f"{self.game_version}.{self.region}.json"

        self.log_path = log_path

        self.region_map = [
            "cs_CZ",
            "el_GR",
            "pl_PL",
            "ro_RO",
            "hu_HU",
            "en_GB",
            "de_DE",
            "es_ES",
            "it_IT",
            "fr_FR",
            "ja_JP",
            "ko_KR",
            "es_MX",
            "es_AR",
            "pt_BR",
            "en_US",
            "en_AU",
            "ru_RU",
            "tr_TR",
            "ms_MY",
            "en_PH",
            "en_SG",
            "th_TH",
            "vn_VN",
            "id_ID",
            "zh_MY",
            "zh_CN",
            "zh_TW",
        ]

    @classmethod
    def _load_json_file(cls, filepath: Path, update=False):
        """
        读取json文件
        :param filepath:
        :param update:
        :return:
        """
        if filepath.exists() and not update:
            return load_json(filepath)
        return {}

    @classmethod
    def _save_json_file(cls, filepath: Path, data, _cls=None):
        """
        保存json文件
        :param filepath:
        :param data:
        :return:
        """
        dump_json(data, filepath, cls=_cls)

    @classmethod
    def file_classify(cls, b, region: str = ""):
        """
        分类, 区分事件和资源文件
        :param b: 好几层的dict
        :param region:
        :return:
        """

        def check_path(paths):
            for p in paths:
                p = p.lower()
                if "_sfx_" in p:
                    return "SFX"
                elif "_vo_" in p:
                    return "VO"
                elif "mus_" in p:
                    return "MUSIC"
                return "SFX"

        region = region.lower()

        for kind in b:
            for name in b[kind]:
                for skin in b[kind][name]:
                    items = b[kind][name][skin]
                    this = defaultdict(list)
                    for item in items:
                        if len(item) == 1:
                            continue
                        _type = check_path(item)

                        events = ""
                        audio = []
                        for path in item:
                            # 哈希表的路径是无所谓大小写(因为最后计算还是按小写+)
                            path = path.lower()
                            if region:
                                path = path.replace("en_us", region)
                            if "events" in path:
                                events = path
                            elif "audio" in path:
                                audio.append(path)
                        this[_type].append({"events": events, "audio": audio})
                    b[kind][name][skin] = this
        return b

    def get_bin_hashes(self, update: bool = False) -> dict:
        """
        穷举皮肤ID， 0~100， 取出bin哈希表
        这个哈希表是用来从wad中提取bin文件用的。
        所以 就算 实际皮肤ID不存在也无所谓。
        :param update: 强制更新
        :return:
        """

        if data := self._load_json_file(self.bin_hash_file, update):
            return data

        # map是整理好的, 几乎没见过更新位置, 所以写死了
        # 如果有新的就直接调用一下 WAD.get_hash(小写路径) 就行了
        result = {
            "characters": {},
            "maps": {
                "common": {"15714053217970310635": "data/maps/shipping/common/common.bin"},
                "map11": {"4648248922051545971": "data/maps/shipping/map11/map11.bin"},
                "map12": {"10561014283630087560": "data/maps/shipping/map12/map12.bin"},
                "map21": {"15820477637625025279": "data/maps/shipping/map21/map21.bin"},
                "map22": {"2513799657867357310": "data/maps/shipping/map22/map22.bin"},
                "map30": {"15079425428213655221": "data/maps/shipping/map30/map30.bin"},
            },
        }
        champion_list = self.game_data.get_champions_name()
        tpl = "data/characters/{}/skins/skin{}.bin"

        for item in champion_list.keys():
            if item == "none":
                continue

            # 循环0 到100， 是skin的编号
            result["characters"].update(
                {item: {WAD.get_hash(tpl.format(item, i)): tpl.format(item, i) for i in range(101)}}
            )

        self._save_json_file(self.bin_hash_file, result)
        return result

    def get_bnk_hashes(self, update: bool = False) -> tree:
        """
        从bin文件中取出实际调用的音频文件列表
        regin不需要实际安装，比如获取其他语言的哈希表，不需要实际安装外服

        :param update: 是否强制更新所有已知哈希表
        :return: 一个tree结构, 就是一个分好类的json
        """

        if res := self._load_json_file(self.bnk_hash_file, update):
            return res
        else:
            bin_hash = self.get_bin_hashes(update)

            res = tree()
            for kind, parts in bin_hash.items():
                # companions为云顶小英雄特效音,
                # 英雄的bin文件中没有事件信息，应该在其他bin里面
                # 但是音频音效都是重复的，也没多大关系，这里就跳过了
                if kind == "companions":
                    continue
                for name, bins in parts.items():

                    if kind == "characters":
                        wad_file = self.game_data.GAME_CHAMPION_PATH / f"{capitalize_first_letter(name)}.wad.client"
                    elif kind == "maps":
                        wad_file = self.game_data.GAME_MAPS_PATH / f"{capitalize_first_letter(name)}.wad.client"
                    else:
                        wad_file = self.game_data.GAME_MAPS_PATH / "Map22.wad.client"

                    if not wad_file.exists():
                        logger.warning(f"文件缺失: {wad_file}......跳过")
                        continue

                    bin_paths = list(bins.values())
                    ids = [Path(item).stem for item in bin_paths]
                    # extract 函数使用 list[path]作为参数, 可保证返回顺序
                    raw_bins = WAD(wad_file).extract(bin_paths, raw=True)

                    bs = []
                    temp = set()
                    for _id, raw in zip(ids, raw_bins):
                        if not raw:
                            continue
                        # 解析Bin文件
                        b = BIN(raw)
                        # 音频文件列表
                        p = b.audio_files
                        # 去重
                        temp, fs = de_duplication(temp, p)
                        if fs:
                            bs.append(b)
                            res[kind][name][_id] = list(fs)
                        elif p:
                            bs.append(b)
                    del raw_bins
                    if bs:
                        self.get_event_hashes(kind, name, bs, True)

            # 这里其实不返回值也可以, 浅拷贝修改
            # res = file_classify(res, GAME_REGION)
            # 傻逼RIOT，zh_cn的文件名字是en_us
            res = self.file_classify(res)

            self._save_json_file(self.bnk_hash_file, res)

        return res

    def get_event_hashes(self, kind, name, bin_datas: list[BIN] = None, update=False) -> list:
        """
        根据bin文件获取事件哈希表
        :param kind:
        :param name:
        :param bin_datas: BIN对象列表，
        :param update:
        :return:
        """
        target = self.event_hash_tpl.format(kind=kind, name=name)
        if res := self._load_json_file(target, update):
            return BIN.load_hash_table(list(res))

        else:
            res = set()
            for bin_data in bin_datas:
                if len(bin_data.hash_tables) == 0:
                    continue
                t = bin_data.hash_tables
                res.update(t)

            res = list(res)
            if res:
                makedirs(target.parent)

                self._save_json_file(target, res, _cls=StringHash.dump_cls())
        del bin_datas
        return res

    def get_audio_hashes(self, items, wad_file, event_hashes, _type, kind, name, skin, update=False) -> None:
        """
        根据提供的信息生成事件ID与音频ID的哈希表
        :param items: 由bin_to_data返回的数据, 格式如下
            {
            "events":
                "assets/sounds/wwise2016/vo/zh_cn/characters/aatrox/skins/base/aatrox_base_vo_events.bnk",
            "audio":
                ["assets/sounds/wwise2016/vo/zh_cn/characters/aatrox/skins/base/aatrox_base_vo_audio.bnk",
                "assets/sounds/wwise2016/vo/zh_cn/characters/aatrox/skins/base/aatrox_base_vo_audio.wpk"]
            }
        :param wad_file: wad文件
        :param event_hashes: get_event_hashes 返回
        :param _type: 音频类型, VO/SFX/MUSIC
        :param kind: 音频类型, characters/companions/maps
        :param name: 英雄或地图名字
        :param skin: 皮肤或地图
        :param update: 是否强制更新
        :return:
        """
        func_name = sys._getframe().f_code.co_name

        warn_item = []
        game_version = self.game_data.get_game_version()

        def tt(value):
            temp = False
            if isinstance(value, list):
                for t in value:
                    temp = temp or t
                return bool(temp)
            return bool(value)

        region_match = re.compile(r"\w{2}_\w{2}").search(str(wad_file))
        region = region_match.group() if region_match and region_match.group() in self.region_map else "Default"

        target = self.audio_hash_tpl.format(type=_type, kind=kind, name=name, skin=skin, region=region)
        if target.exists() and not update:
            # 可以直接pass 这里json加载用来校验文件是否正常
            # d = json.load(open(target, encoding='utf-8'))
            # del d
            # gc.collect()
            pass

        else:
            res = tree()
            parts = wad_file.parts
            index = parts.index("Game")
            relative_wad_path = Path(*parts[index:])
            # relative_wad_path = "Game" + wad_file.split("Game")[-1].replace("\\", "/")
            logger.info(f"开始处理: {kind}, {name}, {skin}, {_type}")
            for item in items:
                if not item["events"]:
                    logger.info(f"无事件文件: {kind}, {name}, {skin}, {_type}")
                    return

                files = [item["events"], *item["audio"]]
                data_raw = WAD(wad_file).extract(files, raw=True)
                if not tt(data_raw):
                    warn_item.append((wad_file, item["events"]))
                    logger.trace(f"WAD无文件解包: {wad_file}, " f'{name}, {skin}, {_type}, {item["events"]}')
                    continue

                # 事件就一个，音频可能有多个，一般是两个
                event_raw, *audio_raw = data_raw
                try:
                    event_hash = league_tools.get_event_hashtable(event_hashes, event_raw)
                except KeyError:
                    # characters, zyra, skin2, SFX, 这个bnk文件events和audio是相反的
                    if len(audio_raw) > 1:
                        raise ValueError(f"未知错误, {kind}, {name}, {skin}, {_type}")
                    event_hash = league_tools.get_event_hashtable(event_hashes, audio_raw[0])
                    audio_raw = [event_raw]

                for raw in audio_raw:
                    audio_hash = league_tools.get_audio_hashtable(event_hash, raw)
                    if audio_hash:
                        # log.info(f'to_audio_hashtable, {kind}, {name}, {skin}, {_type}')
                        res["data"][item["audio"][audio_raw.index(raw)]] = audio_hash
                del event_raw
                del data_raw
                del audio_raw

            if res:
                target.parent.mkdir(parents=True, exist_ok=True)
                res["info"] = {
                    "kind": kind,
                    "name": name,
                    "detail": skin,
                    "type": _type,
                    "region": self.region,
                    "wad": str(relative_wad_path),
                    "version": game_version,
                }

                self._save_json_file(target, res)

            del res
            gc.collect()
            # log.info(f'to_audio_hashtable: {kind}, {name}, {skin}, {_type}')
        if self.log_path:
            _log_file = self.log_path / f"{func_name}.{self.region}.log"
            with _log_file.open("a+", encoding="utf-8") as f:
                for item in warn_item:
                    f.write(f"{item}\n")
