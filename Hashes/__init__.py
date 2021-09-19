# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: PyCharm
# @Create  : 2021/3/4 22:11
# @Update  : 2021/9/19 21:46
# @Detail  : 

import gc
import json
import logging
import os
import re
from collections import defaultdict
from typing import Dict, List

from lol_voice import get_audio_hashtable, get_event_hashtable
from lol_voice.formats import BIN, StringHash, WAD

from Tools import data
from Utils import makedirs, str_get_number, tree
from Utils import downloader

log = logging.getLogger(__name__)
HASH_PATH = os.path.dirname(__file__)
CDTB_PATH = os.path.join(HASH_PATH, 'CDTB', 'cdragontoolbox')
EVENT_HASH_PATH = os.path.join(HASH_PATH, 'event')
E2A_HASH_PATH = os.path.join(HASH_PATH, 'event2audio')
LCU_HASH = os.path.join(CDTB_PATH, 'hashes.lcu.txt')

__all__ = [
    'HASH_PATH',
    'EVENT_HASH_PATH',
    'E2A_HASH_PATH',
    'get_binhash',
    'bin_to_data',
    'bin_to_event',
    'to_audio_hashtable'
]


def get_binhash(update=False) -> Dict:
    """
    根据CDTB提供的哈希表, 取出于所有于语音有关的bin文件
    :param update: 强制更新
    :return:
    """

    target = os.path.join(HASH_PATH, 'bin.json')
    if os.path.exists(target) and not update:
        return json.load(open(target, encoding='utf-8'))
    else:
        return get_binhash_by_local()


def file_classify(b, region):
    """
    分类, 区分事件和资源文件
    :param b:
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
                        path = path.lower().replace('en_us', region)
                        if 'events' in path:
                            events = path
                        elif 'audio' in path:
                            audio.append(path)
                    this[_type].append({'events': events, 'audio': audio})
                b[kind][name][skin] = this
    return b


def bin_to_data(champion_path, common_path, regin, update=False) -> tree:
    """
    根据 filter_hashtable 返回的数据 获取bin文件信息, 事件以及音频文件路径
    :param champion_path: 英雄目录
    :param common_path: 公共资源目录
    :param regin:
    :param update: 是否强制更新所有已知哈希表
    :return:
    """

    def de_duplication(a1, b1):
        """
        去重, 数组套元组, 按元组内的元素去重
        :param a1: 对照组
        :param b1: 待去重数组
        :return: 
        """

        class Stop(Exception):
            pass

        b2 = []
        for item in b1:
            try:
                for i in item:
                    if i not in a1:
                        a1.update(item)
                        b2.append(item)
                        raise Stop
            except Stop:
                continue

        return a1, set(b2)

    target = os.path.join(HASH_PATH, 'audio_file.json')
    if os.path.exists(target) and not update:
        res = json.load(open(target, encoding='utf-8'))
    else:
        bin_hash = get_binhash(update)

        res = tree()
        for kind, parts in bin_hash.items():
            # companions为云顶小英雄特效音, bin文件中没有事件信息
            if kind == 'companions':
                continue
            for name, bins in parts.items():

                if kind == 'characters':
                    wad_file = os.path.join(champion_path, f'{name.capitalize()}.wad.client')
                elif kind == 'maps':
                    wad_file = os.path.join(common_path, f'{name.capitalize()}.wad.client')
                else:
                    wad_file = os.path.join(common_path, 'Map22.wad.client')

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
                    bin_to_event(kind, name, bs, True)

        # 这里其实不返回值也可以, 浅拷贝修改
        res = file_classify(res, regin)
        with open(target, 'w+', encoding='utf-8') as f:
            json.dump(res, f)
    return res


def bin_to_event(kind, name, bin_datas: List[BIN] = None, update=False):
    """
    根据bin文件获取事件哈希表
    :param kind: 
    :param name: 
    :param bin_datas: 
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

        if res:
            makedirs(os.path.dirname(target))
            with open(target, 'w+', encoding='utf-8') as f:
                json.dump(list(res), f, cls=StringHash.dump_cls())
    del bin_datas
    return res


def to_audio_hashtable(items, wad_file, bin_data, _type, kind, name, skin, update=False):
    """
    根据提供的信息生成音频ID哈希表
    :param items: 由bin_to_data返回的数据, 格式如下
        {
        "events":
            "assets/sounds/wwise2016/vo/zh_cn/characters/aatrox/skins/base/aatrox_base_vo_events.bnk",
        "audio":
            ["assets/sounds/wwise2016/vo/zh_cn/characters/aatrox/skins/base/aatrox_base_vo_audio.bnk",
            "assets/sounds/wwise2016/vo/zh_cn/characters/aatrox/skins/base/aatrox_base_vo_audio.wpk"]
        }
    :param wad_file: wad文件
    :param bin_data: bin_to_event 返回
    :param _type: 音频类型, VO/SFX/MUSIC
    :param kind: 音频类型, characters/companions/maps
    :param name: 英雄或地图名字
    :param skin: 皮肤或地图
    :param update: 是否强制更新
    :return:
    """

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
                log.warning(f'无事件文件: {kind}, {name}, {skin}, {_type}')
                return

            files = [item['events'], *item['audio']]
            data_raw = WAD(wad_file).extract(files, raw=True)
            if not tt(data_raw):
                # log.warning(f'WAD无文件解包: {wad_file}, {name}, {skin}, {_type}, {item["events"]}')
                continue
            event_raw, *audio_raw = data_raw
            try:
                event_hash = get_event_hashtable(bin_data, event_raw)
            except KeyError:
                # characters, zyra, skin2, SFX, 这个bnk文件events和audio是相反的
                if len(audio_raw) > 1:
                    raise ValueError(f'未知错误, {kind}, {name}, {skin}, {_type}')
                event_hash = get_event_hashtable(bin_data, audio_raw[0])
                audio_raw = [event_raw]

            for raw in audio_raw:
                audio_hash = get_audio_hashtable(event_hash, raw)
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


def get_binhash_by_local():
    """
    穷举
    :return:
    """
    result = {
        "characters": {},
        "maps": {
            "common": {
                "15714053217970310635": "data/maps/shipping/common/common.bin"
            },
            "map11": {"4648248922051545971": "data/maps/shipping/map11/map11.bin"},
            "map12": {"10561014283630087560": "data/maps/shipping/map12/map12.bin"},
            "map21": {"15820477637625025279": "data/maps/shipping/map21/map21.bin"},
            "map22": {"2513799657867357310": "data/maps/shipping/map22/map22.bin"}
        }}
    champion_list = data.get_champions_name()
    tpl = 'data/characters/{}/skins/skin{}.bin'

    for item in champion_list.keys():
        if item == 'none':
            continue
        result['characters'].update({item: {WAD.get_hash(tpl.format(item, i)): tpl.format(item, i) for i in range(101)}})
    target = os.path.join(HASH_PATH, 'bin.json')
    with open(target, 'w+') as f:
        json.dump(result, f)
    return result
