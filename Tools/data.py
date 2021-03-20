# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: PyCharm
# @Create  : 2021/2/25 1:40
# @Update  : 2021/3/21 0:19
# @Detail  : 获取英雄数据

import os
import json
import Data
import logging
from lol_voice.formats import WAD
from Utils import downloader, format_region
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)


def update_data_by_cdragon(region='zh_cn'):
    """
    更新游戏数据
    :return:
    """
    if region == 'en_us':
        region = 'default'
    save_path = Data.DATA_PATH % region
    update_list = [
        'champion-summary.json',
        'skins.json'
    ]
    url = f'https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/{region}/v1/'
    for item in update_list:
        downloader.get(f'{url}{item}', os.path.join(save_path, os.path.basename(item)))

    with open(os.path.join(save_path, update_list[0]), encoding='utf-8') as f:
        summary = json.load(f)
        with ThreadPoolExecutor() as executor:
            for item in summary:
                name = f'{item["id"]}.json'
                executor.submit(downloader.get, f'{url}champions/{name}',
                                os.path.join(Data.DATA_CHAMPIONS_PATH, f'{name}'))


def update_data_by_local(game_path, region='zh_cn'):
    """
    根据根本游戏文件获取 数据文件
    :param game_path:
    :param region:
    :return:
    """
    if region == 'en_us':
        region = 'default'

    def output_file_name(path):
        old = f'plugins/rcp-be-lol-game-data/global/{region}/v1/'
        new = path.replace(old, '')
        return os.path.join(Data.DATA_PATH % region, os.path.normpath(new))

    data_path = os.path.join(game_path, 'LeagueClient', 'Plugins', 'rcp-be-lol-game-data')

    wad_file = os.path.join(data_path, f'{format_region(region)}-assets.wad')
    hash_table = [
        f'plugins/rcp-be-lol-game-data/global/{region}/v1/champion-summary.json',
        f'plugins/rcp-be-lol-game-data/global/{region}/v1/skinlines.json',
        f'plugins/rcp-be-lol-game-data/global/{region}/v1/skins.json',
        f'plugins/rcp-be-lol-game-data/global/{region}/v1/maps.json',
        f'plugins/rcp-be-lol-game-data/global/{region}/v1/universes.json'
    ]
    WAD(wad_file).extract(hash_table, out_dir=output_file_name)
    WAD(wad_file).extract(
        [f'plugins/rcp-be-lol-game-data/global/{region}/v1/champions/{item["id"]}.json' for item in get_summary()],
        out_dir=output_file_name)


def get_summary(region='zh_cn'):
    return json.load(open(Data.DATA_SUMMARY % region, encoding='utf-8'))


def get_skins(region='zh_cn'):
    return json.load(open(Data.DATA_SKINS % region, encoding='utf-8'))


def get_maps(region='zh_cn'):
    return json.load(open(Data.DATA_MAPS % region, encoding='utf-8'))


def get_champion_detail_by_id(cid, region='zh_cn'):
    return json.load(open(os.path.join(Data.DATA_CHAMPIONS_PATH % region, f'{cid}.json'), encoding='utf-8'))


def get_champion_name(name, chinese=True):
    """
    根据游戏数据获取中文名称
    :param name:
    :param chinese:
    :return:
    """
    summary = get_summary()
    for item in summary:
        if item['alias'].lower() == name.lower():
            if chinese:
                return item['alias'], item['name']
            else:
                return item['alias']


def get_champions_name():
    return {item['alias'].lower(): item['name'] for item in get_summary()}


def get_champions_id():
    return [item['id'] for item in get_summary()]


def get_maps_id():
    return [item['id'] for item in get_maps()]
