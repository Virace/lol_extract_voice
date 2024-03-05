# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2022/8/26 14:11
# @Update  : 2024/3/6 6:50
# @Detail  : 描述

import gc
import json
import os
import re
import sys
from collections import defaultdict
from typing import Dict, List

import lol_voice
from loguru import logger
from lol_voice.formats import BIN, StringHash, WAD

from Data.Manifest import GameData
from Utils.common import de_duplication, makedirs, tree
from config import GAME_CHAMPION_PATH, GAME_MAPS_PATH, GAME_REGION, HASH_PATH, LOG_PATH

EVENT_HASH_PATH = os.path.join(HASH_PATH, 'event')
E2A_HASH_PATH = os.path.join(HASH_PATH, 'event2audio')
makedirs(EVENT_HASH_PATH)
makedirs(E2A_HASH_PATH)

# 游戏数据相关
game_data = GameData()
game_data_default = GameData('en_us')


def file_classify(b, region='') -> tree:
    """
    分类, 区分事件和资源文件
    :param b: 好几层的dict
    :param region:
    :return:
    """

    def check_path(paths):
        for p in paths:
            p = p.lower()
            if '_sfx_' in p:
                return 'SFX'
            elif '_vo_' in p:
                return 'VO'
            elif 'mus_' in p:
                return 'MUSIC'
            return 'SFX'

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

                    events = ''
                    audio = []
                    for path in item:
                        # 哈希表的路径是无所谓大小写(因为最后计算还是按小写+)
                        path = path.lower()
                        if region:
                            path = path.replace('en_us', region)
                        if 'events' in path:
                            events = path
                        elif 'audio' in path:
                            audio.append(path)
                    this[_type].append({'events': events, 'audio': audio})
                b[kind][name][skin] = this
    return b


def get_bin_hashes(update=False) -> Dict:
    """
    穷举皮肤ID， 0~100， 取出bin哈希表
    这个哈希表是用来从wad中提取bin文件用的。
    所以 就算 实际皮肤ID不存在也无所谓。
    :param update: 强制更新
    :return:
    """
    target = os.path.join(HASH_PATH, 'bin.json')
    if os.path.exists(target) and not update:
        return json.load(open(target, encoding='utf-8'))

    # map是整理好的, 几乎没见过更新位置, 所以写死了
    # 如果有新的就直接调用以下 WAD.get_hash(小写路径) 就行了
    result = {
        "characters": {},
        "maps": {
            "common": {
                "15714053217970310635": "data/maps/shipping/common/common.bin"
            },
            "map11": {"4648248922051545971": "data/maps/shipping/map11/map11.bin"},
            "map12": {"10561014283630087560": "data/maps/shipping/map12/map12.bin"},
            "map21": {"15820477637625025279": "data/maps/shipping/map21/map21.bin"},
            "map22": {"2513799657867357310": "data/maps/shipping/map22/map22.bin"},
            "map30": {"15079425428213655221": "data/maps/shipping/map30/map30.bin"}
        }}
    champion_list = game_data.get_champions_name()
    tpl = 'data/characters/{}/skins/skin{}.bin'

    for item in champion_list.keys():
        if item == 'none':
            continue

        # 循环0 到100， 是skin的编号
        result['characters'].update(
            {item: {WAD.get_hash(tpl.format(item, i)): tpl.format(item, i) for i in range(101)}})

    with open(target, 'w+') as f:
        json.dump(result, f)
    return result


def get_bnk_hashes(update=False) -> tree:
    """
    从bin文件中取出实际调用的音频文件列表
    regin不需要实际安装，比如获取其他语言的哈希表，不需要实际安装外服

    :param update: 是否强制更新所有已知哈希表
    :return: 一个tree结构, 就是一个分好类的json
    """

    target = os.path.join(HASH_PATH, f'bnk.{GAME_REGION}.json')
    if os.path.exists(target) and not update:
        res = json.load(open(target, encoding='utf-8'))
    else:
        bin_hash = get_bin_hashes(update)

        res = tree()
        for kind, parts in bin_hash.items():
            # companions为云顶小英雄特效音, 英雄的bin文件中没有事件信息，应该在其他bin里面
            # 但是音频音效都是重复的，也没多大关系，这里就跳过了
            if kind == 'companions':
                continue
            for name, bins in parts.items():

                if kind == 'characters':
                    wad_file = os.path.join(GAME_CHAMPION_PATH, f'{name.capitalize()}.wad.client')
                elif kind == 'maps':
                    wad_file = os.path.join(GAME_MAPS_PATH, f'{name.capitalize()}.wad.client')
                else:
                    wad_file = os.path.join(GAME_MAPS_PATH, 'Map22.wad.client')

                bin_paths = list(bins.values())
                ids = [os.path.splitext(os.path.basename(item))[0] for item in bin_paths]
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
                    else:
                        if p:
                            bs.append(b)
                del raw_bins
                if bs:
                    get_event_hashes(kind, name, bs, True)

        # 这里其实不返回值也可以, 浅拷贝修改
        # res = file_classify(res, GAME_REGION)
        # 傻逼RIOT，zh_cn的文件名字是en_us
        res = file_classify(res)
        with open(target, 'w+', encoding='utf-8') as f:
            json.dump(res, f)
    return res


def get_event_hashes(kind, name, bin_datas: List[BIN] = None, update=False) -> List:
    """
    根据bin文件获取事件哈希表
    :param kind:
    :param name:
    :param bin_datas: BIN对象列表，
    :param update:
    :return:
    """
    target = os.path.join(HASH_PATH, 'event', kind, f'{name}.json')
    if os.path.exists(target) and not update:
        res = BIN.load_hash_table(target)
    else:
        res = set()
        for bin_data in bin_datas:
            if len(bin_data.hash_tables) == 0:
                continue
            t = bin_data.hash_tables
            res.update(t)

        res = list(res)
        if res:
            makedirs(os.path.dirname(target))
            with open(target, 'w+', encoding='utf-8') as f:
                json.dump(res, f, cls=StringHash.dump_cls())
    del bin_datas
    return res


def get_audio_hashes(items, wad_file, event_hashes, _type, kind, name, skin, update=False) -> None:
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
    _log_file = os.path.join(LOG_PATH, f'{func_name}.{GAME_REGION}.log')
    warn_item = []

    def tt(value):
        temp = False
        if isinstance(value, list):
            for t in value:
                temp = temp or t
            return bool(temp)
        return bool(value)

    region = re.compile(r'\w{2}_\w{2}').search(wad_file)
    if region:
        region = region.group()
    else:
        region = 'Default'
    target = os.path.join(HASH_PATH, 'event2audio', region, _type, kind, name,
                          f'{skin}.json')
    if os.path.exists(target) and not update:
        # 可以直接pass 这里json加载用来校验文件是否正常
        # d = json.load(open(target, encoding='utf-8'))
        # del d
        # gc.collect()
        pass

    else:
        res = tree()
        relative_wad_path = 'Game' + wad_file.split('Game')[-1].replace('\\', '/')
        for item in items:
            if not item['events']:
                logger.info(f'无事件文件: {kind}, {name}, {skin}, {_type}')
                return

            files = [item['events'], *item['audio']]
            data_raw = WAD(wad_file).extract(files, raw=True)
            if not tt(data_raw):
                warn_item.append((wad_file, item["events"]))
                logger.trace(f'WAD无文件解包: {wad_file}, {name}, {skin}, {_type}, {item["events"]}')
                continue

            # 事件就一个，音频可能有多个，一般是两个
            event_raw, *audio_raw = data_raw
            try:
                event_hash = lol_voice.get_event_hashtable(event_hashes, event_raw)
            except KeyError:
                # characters, zyra, skin2, SFX, 这个bnk文件events和audio是相反的
                if len(audio_raw) > 1:
                    raise ValueError(f'未知错误, {kind}, {name}, {skin}, {_type}')
                event_hash = lol_voice.get_event_hashtable(event_hashes, audio_raw[0])
                audio_raw = [event_raw]

            for raw in audio_raw:
                audio_hash = lol_voice.get_audio_hashtable(event_hash, raw)
                if audio_hash:
                    # log.info(f'to_audio_hashtable, {kind}, {name}, {skin}, {_type}')
                    res['data'][item['audio'][audio_raw.index(raw)]] = audio_hash
            del event_raw
            del data_raw
            del audio_raw

        if res:
            path = os.path.dirname(target)

            makedirs(path)
            res['info'] = {
                'kind': kind,
                'name': name,
                'detail': skin,
                'type': _type,
                'wad': relative_wad_path
            }
            with open(target, 'w+', encoding='utf-8') as f:
                json.dump(res, f)
        del res
        gc.collect()
        # log.info(f'to_audio_hashtable: {kind}, {name}, {skin}, {_type}')

    with open(_log_file, 'a+', encoding='utf-8') as f:
        for item in warn_item:
            f.write(f'{item}\n')
