# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2022/8/15 23:53
# @Update  : 2022/8/27 13:26
# @Detail  : 描述

import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from typing import Union

import lol_voice
from loguru import logger
from lol_voice.formats import WAD

from Hashes import E2A_HASH_PATH, game_data, get_audio_hashes, get_bnk_hashes, get_event_hashes
from Utils.common import format_region, makedirs
from Utils.logs import log_result
from config import AUDIO_PATH, EXCLUDE_TYPE, GAME_CHAMPION_PATH, GAME_LCU_PATH, GAME_MAPS_PATH, GAME_PATH, GAME_REGION, \
    HASH_PATH, \
    LOG_PATH, \
    MANIFEST_PATH, \
    TEMP_PATH, VGMSTREAM_PATH


def get_wad_file_name(kind, name, _type, region) -> Union[str, os.PathLike]:
    """
    根据条件拼接wad文件路径
    :param kind: 英雄 、地图
    :param name: 名字
    :param _type: 台词、音效
    :param region: 区域
    :return:
    """
    region2 = region[:3].lower() + region[3:].upper()
    if kind == 'companions':
        name = 'map22'

    path = GAME_CHAMPION_PATH if kind == 'characters' else GAME_MAPS_PATH

    filename = f'{name.capitalize()}.wad.client'
    if _type == 'VO' and region2 != 'en_US':
        filename = f'{name.capitalize()}.{region2}.wad.client'

    return os.path.join(path, filename)


def get_event_audio_hash_table(update=False, max_works=None) -> None:
    """
    给定游戏英雄以及公共文件目录和区域语言, 获取出小小英雄外可获取的所有音频事件与音频资源ID对应哈希表
    :param update:
    :param max_works
    :return:
    """
    # 获取bnk\wpk文件哈希表
    logger.info(rf'开始获取bnk\wpk文件哈希表, 强制更新: {update}')
    bnk_hashes = get_bnk_hashes(update)
    logger.info(rf'获取bnk\wpk文件哈希表完成')

    logger.info('开始提取音频哈希表.')
    with ProcessPoolExecutor(max_workers=max_works) as e:
        fs = {}
        for kind, sections in bnk_hashes.items():
            # 排除小小英雄
            if kind == 'companions':
                continue

            # 循环英雄、和 皮肤
            for name, skins in sections.items():
                for skin, paths in skins.items():

                    event_hashes = get_event_hashes(kind, name)

                    for _type, value in paths.items():
                        # if not(kind == 'characters' and name == 'akali' and skin == 'skin61' and _type == 'SFX'):
                        #     continue

                        wad_file = get_wad_file_name(kind, name, _type, GAME_REGION)
                        # get_audio_hashes(value, wad_file, bin_data, _type, kind, name,
                        #                  skin, update)
                        fs.update(
                            {e.submit(get_audio_hashes, value, wad_file, event_hashes, _type, kind, name,
                                      skin, update): f'{kind}, {name}, {skin}, {_type}'
                             })

        log_result(fs, sys._getframe().f_code.co_name)
        logger.info('提取音频哈希表完毕.')


def get_lcu_audio():
    """
    提取LCU ban 选以及效果 音频资源
    :return:
    """
    sfx = []
    vo = []

    def output_file_name(_r):
        def get_path(path):
            rep = f'plugins/rcp-be-lol-game-data/global/{_r}/v1/'
            new = path.replace(rep, '')
            return os.path.join(AUDIO_PATH, _r, 'LCU', os.path.normpath(new))

        return get_path

    wad_sfx_file = os.path.join(GAME_LCU_PATH, 'default-assets.wad')
    wad_vo_file = os.path.join(GAME_LCU_PATH, f'{format_region(GAME_REGION)}-assets.wad')
    for cid in game_data.get_champions_id():
        sfx.append(f'plugins/rcp-be-lol-game-data/global/default/v1/champion-sfx-audios/{cid}.ogg')
        vo.extend([f'plugins/rcp-be-lol-game-data/global/{GAME_REGION}/v1/champion-choose-vo/{cid}.ogg',
                   f'plugins/rcp-be-lol-game-data/global/{GAME_REGION}/v1/champion-ban-vo/{cid}.ogg'])

    WAD(wad_sfx_file).extract(sfx, out_dir=output_file_name('default'))
    WAD(wad_vo_file).extract(vo, out_dir=output_file_name(GAME_REGION))


def get_game_audio(hash_path=E2A_HASH_PATH, audio_format='wav', max_works=None):
    """
    根据提供的哈希表, 提取游戏音频资源
    如果默认则为全部哈希表
    如果只需要更新部分英雄，则将部分哈希表放在指定目录，传入即可
    :param hash_path: 哈希表路径, 默认为E2A_HASH_PATH
    :param audio_format: 音频转码格式
    :param max_works: 最大进程数
    :return:
    """
    logger.info(f'开始提取游戏内音频. hash_path:{hash_path}, audio_format:{audio_format}')
    with ProcessPoolExecutor(max_workers=max_works) as e:
        fs = dict()
        for root, dirs, files in os.walk(hash_path):

            # 排除不需要的文件夹
            _tt = os.path.basename(os.path.dirname(os.path.dirname(root)))
            if files and _tt in EXCLUDE_TYPE:
                continue

            for file in files:
                ext = os.path.splitext(file)[-1]
                if ext == '.json':
                    with open(os.path.join(root, file), encoding='utf-8') as f:
                        data = json.load(f)
                        _type = data['info']['type']
                        kind = data['info']['kind']
                        name = data['info']['name']
                        detail = data['info']['detail']
                        logger.info(f'获取{kind} {name} {detail} {_type}音频')
                        # 拼接wad文件名字
                        wad_file = os.path.join(GAME_PATH, os.path.normpath(data['info']['wad']))

                        # 取出bnk音频文件 字节类型
                        audio_raws = WAD(wad_file).extract(list(data['data'].keys()), raw=True)
                        for raw in audio_raws:
                            if raw:
                                # 解析bnk文件
                                audio_files = lol_voice.get_audio_files(raw)
                                del raw
                                for i in audio_files:
                                    thisname = i.filename if i.filename else f'{i.id}.wem'
                                    filename = os.path.join(
                                        AUDIO_PATH, GAME_REGION if _type == 'VO' else 'default',
                                        _type, kind, name, detail,
                                        thisname.replace('wem', audio_format)
                                    )

                                    makedirs(os.path.dirname(filename))
                                    # i.static_save_file(i.data, filename, False, vgmstream_cli)
                                    fs[e.submit(i.static_save_file, i.data, filename, False, VGMSTREAM_PATH)] = (
                                        _type, kind, name, detail, wad_file)

        log_result(fs, sys._getframe().f_code.co_name)
        logger.info('提取游戏内音频完毕.')


def main(audio_format='wem', max_works=None):
    """
    获取游戏内 音频文件
    :param audio_format: 音频格式
    :param max_works: 最大线程数
    :return:
    """
    # 更新英雄列表等数据
    game_data.update_data()

    # 更新哈希表
    get_event_audio_hash_table()

    get_lcu_audio()
    get_game_audio(audio_format, max_works)


def init():
    # 初始化目录
    makedirs(TEMP_PATH)
    makedirs(LOG_PATH, True)
    makedirs(HASH_PATH)
    makedirs(MANIFEST_PATH)


if __name__ == '__main__':
    init()
    main(audio_format='wav')
