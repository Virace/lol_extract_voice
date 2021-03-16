# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: PyCharm
# @Create  : 2021/2/25 1:40
# @Update  : 2021/3/12 0:40
# @Detail  : 获取英雄数据

import os
import json
import Champions
import logging
from Utils import downloader
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)


def update_champions():
    """
    更新英雄数据
    :return:
    """
    save_path = Champions.CHAMPIONS_PATH
    update_list = [
        'champion-summary.json',
        'skins.json'
    ]
    url = 'https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/zh_cn/v1/'
    for item in update_list:
        downloader.get(f'{url}{item}', os.path.join(save_path, os.path.basename(item)))

    with open(os.path.join(save_path, update_list[0]), encoding='utf-8') as f:
        summary = json.load(f)
        with ThreadPoolExecutor() as executor:
            for item in summary:
                name = f'{item["id"]}.json'
                executor.submit(downloader.get, f'{url}champions/{name}',
                                os.path.join(Champions.CHAMPIONS_DETAILED_PATH, f'{name}'))


def get_summary():
    return json.load(open(Champions.CHAMPIONS_SUMMARY, encoding='utf-8'))


def get_skins():
    return json.load(open(Champions.CHAMPIONS_SKINS, encoding='utf-8'))


def get_detail_by_id(cid):
    return json.load(open(os.path.join(Champions.CHAMPIONS_DETAILED_PATH, f'{cid}.json'), encoding='utf-8'))


def get_name(name, chinese=True):
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


def get_names():
    return {item['alias'].lower(): item['name'] for item in get_summary()}
