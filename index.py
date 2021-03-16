# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: PyCharm
# @Create  : 2021/2/24 23:29
# @Update  : 2021/3/16 14:4
# @Detail  : 解包英雄联盟语音文件


import json
import logging
import os
from concurrent.futures import ProcessPoolExecutor, as_completed

from lol_voice import get_audio_files
from lol_voice.formats import WAD

from Hashes import bin_to_data, bin_to_event, to_audio_hashtable, E2A_HASH_PATH
from Utils import makedirs
from Utils.wrapper import check_time

log = logging.getLogger(__name__)


def get_wad_file_name(champion_path, common_path, kind, name, _type, region):
    region2 = region[:3].lower() + region[3:].upper()
    if kind == 'companions':
        name = 'map22'

    path = common_path
    if kind == 'characters':
        path = champion_path

    filename = f'{name.capitalize()}.wad.client'
    if _type == 'VO' and region2 != 'en_US':
        filename = f'{name.capitalize()}.{region2}.wad.client'

    return os.path.join(path, filename)


@check_time
def get_event_audio_hash_table(champion_path, common_path, region, update=False, max_works=None):
    """
    给定游戏英雄以及公共文件目录和区域语言, 获取出小小英雄外可获取的所有音频事件与音频资源ID对应哈希表
    :param champion_path:
    :param common_path:
    :param region: zh_cn
    :param update:
    :param max_works
    :return:
    """
    b = bin_to_data(champion_path, common_path, region, update)

    with ProcessPoolExecutor(max_workers=max_works) as e:
        fs = {}
        for kind, sections in b.items():
            if kind == 'companions':
                continue
            for name, skins in sections.items():
                for skin, paths in skins.items():
                    # raw_files = [WAD(name).extract(item, raw=True) for item in paths]
                    bin_data = bin_to_event(kind, name)
                    for _type, value in paths.items():

                        if kind == 'characters' and name == 'swain' and skin == 'skin2' and _type == 'VO':
                            continue

                        wad_file = get_wad_file_name(champion_path, common_path, kind, name, _type, region)

                        # log.info(f'{kind}, {name}, {skin}, {_type}')
                        # to_audio_hashtable(value, wad_file, bin_data, _type, kind, name, skin)
                        fs.update(
                            {e.submit(to_audio_hashtable, value, wad_file, bin_data, _type, kind, name,
                                      skin, update): f'{kind}, {name}, {skin}, {_type}'
                             })

        for f in as_completed(fs):
            try:
                f.result()
            except Exception as exc:
                log.warning(f'generated an exception: {exc}, {fs[f]}')
            else:
                log.info(f'Done. {fs[f]}')


@check_time
def main(game_path, out_dir, vgmstream_cli, region=None, audio_format='wem', max_works=None):
    """
    获取语音事件语音ID对应表, 并且解包所有音频文件
    :param game_path: 游戏根目录
    :param out_dir:
    :param vgmstream_cli:
    :param region: 提取的区域与语言, 默认zh_cn
    :param audio_format:
    :param max_works:
    :return:
    """
    champion_path = os.path.join(game_path, 'Game', 'DATA', 'FINAL', 'Champions')
    common_path = os.path.join(game_path, 'Game', 'DATA', 'FINAL', 'Maps', 'Shipping')

    # 约使用75秒左右
    get_event_audio_hash_table(champion_path, common_path, region)
    with ProcessPoolExecutor(max_workers=max_works) as e:
        fs = dict()
        for root, dirs, files in os.walk(E2A_HASH_PATH):
            if 'SFX' in root:
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
                        wadfile = os.path.join(game_path, os.path.normpath(data['info']['wad']))

                        audio_raws = WAD(wadfile).extract(list(data['data'].keys()), raw=True)
                        for raw in audio_raws:
                            if raw:
                                audio_files = get_audio_files(raw)
                                del raw
                                for i in audio_files:
                                    thisname = i.filename if i.filename else f'{i.id}.wem'
                                    filename = os.path.join(
                                        out_dir,
                                        _type, kind, name, detail,
                                        thisname.replace('wem', audio_format)
                                    )
                                    makedirs(os.path.dirname(filename))
                                    # i.save_file(filename, False,
                                    #             r"D:\Games\Ol\Tools\Temps\bin\vgmstream-win\test.exe")
                                    fs[e.submit(i.static_save_file, i.data, filename, False, vgmstream_cli)] = (
                                        _type, kind, name, detail, wadfile)

        for f in as_completed(fs):
            try:
                f.result()
            except Exception as exc:
                log.warning(f'generated an exception: {exc}, {fs[f]}')
            else:
                # log.info(f'Done. {fs[f]}')
                pass

