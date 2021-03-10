# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: PyCharm
# @Create  : 2021/2/24 23:29
# @Update  : 2021/3/10 22:54
# @Detail  : 解包英雄联盟语音文件


import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict

from lol_voice import extract_audio
from lol_voice.formats import BIN, WAD

import Hashes
from Utils.wrapper import check_time


def dict_update(data, key, value, new: Callable = list, call='append'):
    if key not in data:
        data[key] = new()

    getattr(data[key], call)(value)
    return data


@check_time
def filter_hashtable(region, update=False) -> Dict:
    """
    根据CDTB提供的哈希表, 取出于当前 地区 有关的所有音频文件哈希表
    :param region: 区域, 例如: zh_cn
    :param update: 强制更新
    :return:
    """
    target = os.path.join(os.path.dirname(Hashes.GAME), f'{region}.json')
    if os.path.exists(target) and not update:
        res = json.load(open(target, encoding='utf-8'))
    else:
        res = {}
        with open(Hashes.GAME) as f:
            for line in f:

                h, p = line.replace('\n', '').split(' ', 1)
                ext = p[-4:]

                if ext in ['.bnk', '.wpk']:
                    if 'wwise2016' not in line:
                        # 只筛选新版文件
                        continue
                elif ext in ['.bin']:
                    pass
                else:
                    continue

                this = {str(int(h, 16)): p}
                item = p.split('/')
                count = len(item)

                if ext == '.bin':
                    if count == 5:
                        # 皮肤bin、地图bin、很多bin

                        if item[3] == 'skins' or item[2] == 'shipping':
                            res.update(this)
                else:
                    if count == 6:
                        # 地图效果音
                        res.update(this)
                    elif count == 7:
                        # 地图NPC语音
                        if item[4] == region.lower():
                            res.update(this)
                    elif count == 9:
                        # 效果音
                        if 'companions' in p:
                            # 下棋的效果音?, 没下过棋不清楚
                            res.update(this)
                        else:
                            # name = item[5]
                            # skin = item[7]
                            # 英雄效果音
                            res.update(this)
                    elif count == 10:
                        # 英雄语音
                        # 升级处理 getattr setattr
                        if item[4] == region.lower():
                            # name = item[6]
                            # skin = item[8]

                            res.update(this)

        with open(os.path.join(os.path.dirname(Hashes.GAME), f'{region}.json'), 'w+', encoding='utf-8') as f:
            json.dump(res, f)
    return res


@check_time
def bin_info(path, region, update=False) -> Dict:
    """
    解析bin文件, 获取事件哈希表 以及 音频文件对应哈希表
    :param path: 搜寻BIN文件路径, 主函数Temp目录
    :param region: 地区
    :param update: 是否强制更新所有已知哈希表
    :return:
    """
    target = os.path.join(os.path.dirname(Hashes.GAME), f'bin_{region}.json')
    if os.path.exists(target) and not update:
        res = json.load(open(target, encoding='utf-8'))
    else:
        res = {}
        temp = list()
        for root, dirs, files in os.walk(path):
            if files:
                for file in files:
                    sf = os.path.splitext(file)
                    if sf[-1] == '.bin':
                        bin_file = os.path.join(root, file)
                        b = BIN(os.path.join(root, file))
                        if b.hash_tables:
                            print(root, file)
                            fs = set(b.get_audio_files())
                            fs.difference_update(set(temp))
                            if fs:
                                with open(os.path.join(root, f'{sf[0]}_bin.json'), 'w+', encoding='utf-8') as f:
                                    json.dump(b.get_hash_table(), f)
                                fl = list(fs)
                                res.update({bin_file: fl})
                                temp.extend(fl)
        with open(target, 'w+', encoding='utf-8') as f:
            json.dump(res, f)
    return res


@check_time
def main(game_path, region, out_path):
    hashtable = filter_hashtable(region, True)

    champion_path = os.path.join(game_path, 'Game', 'DATA', 'FINAL', 'Champions')
    common_path = os.path.join(game_path, 'Game', 'DATA', 'FINAL', 'Maps', 'Shipping')

    # 获取所有英雄文件名, 筛选设置中对应的国家, 并排除SG文件
    champion_files = [item for item in os.listdir(champion_path)
                      if item.lower().find(region) > 0 or (item.find('_') < 0 and item.lower().find('sg_'))]

    # 获取公共部分文件名, 筛选设置中对应的国家, 并添加几个公共文件, 排除LEVELS文件因为不包含语音文件
    common_files = [item for item in os.listdir(common_path)
                    if item.lower().find(region) > 0 or (item.find('_') < 0 and item.find('LEVELS') < 0)]

    # # 划分WAD解包临时目录
    temp_path = os.path.join(out_path, 'Temps')
    if not os.path.exists(temp_path):
        os.mkdir(temp_path)

    # 划分WAV文件目录
    res_path = os.path.join(out_path, 'Res')
    if not os.path.exists(res_path):
        os.mkdir(res_path)

    all_wad = [*[(os.path.join(champion_path, item), temp_path) for item in
                 champion_files],
               *[(os.path.join(common_path, item), temp_path) for item in
                 common_files]]


    # 根据哈希表创建文件夹, 防止线程池内函数创建文件夹出错
    for _, path in hashtable.items():
        directory = os.path.dirname(os.path.join(temp_path, os.path.normpath(path)))
        if not os.path.exists(directory):
            os.makedirs(directory)

    # 并发解包wad, 这一环节吃内存写入和硬盘读取, 修改max_workers调整并发数
    with ThreadPoolExecutor(max_workers=16) as executor:
        future_to_path = {executor.submit(WAD(item[0]).extract_hash, hashtable, item[1]): item for item in
                          all_wad}
        for future in as_completed(future_to_path):
            url = future_to_path[future]
            try:
                data = future.result()
            except Exception as exc:
                print('%r generated an exception: %s' % (url, exc))

    hashtable_bin = bin_info(temp_path, region)
    extract_data = []
    for key, value in hashtable_bin.items():
        data = BIN.load_hash_table(f'{os.path.splitext(key)[0]}_bin.json')
        for item in value:
            audio = []
            event = ''
            out = ''
            for a in item:
                this = os.path.join(temp_path, os.path.normpath(a.lower().replace('en_us', region)))
                if 'events' in a:
                    event = this
                    out = os.path.join(res_path, os.path.normpath(
                        os.path.dirname(a).replace('ASSETS/Sounds/Wwise2016/', '').replace('/Skins', '').replace(
                            'en_US/', '')))
                    if not os.path.exists(out):
                        os.makedirs(out)
                else:
                    audio.append(this.replace('en_us', region))
            for a in audio:
                extract_data.append((data, event, a, out))


    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = {executor.submit(extract_audio, item[0], item[1], item[2], item[3]): item for item in extract_data}
        for future in as_completed(futures):
            data = futures[future]
            try:
                future.result()
            except Exception as exc:
                print('%r generated an exception: %s' % (data, exc))

