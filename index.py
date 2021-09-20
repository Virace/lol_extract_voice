# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: PyCharm
# @Create  : 2021/2/24 23:29
# @Update  : 2021/9/20 10:17
# @Detail  : 解包英雄联盟语音文件


import json
import logging
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
import itertools
import requests
from lol_voice import get_audio_files
from lol_voice.formats import WAD

from Hashes import bin_to_data, bin_to_event, to_audio_hashtable, E2A_HASH_PATH
from Tools.data import get_champions_id, update_data_by_local, get_game_version_by_local
from Utils import makedirs, format_region
from Utils.wrapper import check_time
from config import LOCAL_VERSION_FILE

log = logging.getLogger(__name__)


def get_wad_file_name(champion_path, common_path, kind, name, _type, region):
    """
    根据条件拼接wad文件路径
    :param champion_path:
    :param common_path:
    :param kind:
    :param name:
    :param _type:
    :param region:
    :return:
    """
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
                        # if kind == 'characters' and name == 'swain' and skin == 'skin2' and _type == 'VO':
                        #     continue

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
def get_lcu_audio(data_path, out_dir, region='zh_cn'):
    """
    提取LCU ban 选以及效果 音频资源
    :param data_path:
    :param region:
    :param out_dir:
    :return:
    """
    sfx = []
    vo = []
    if region == 'en_us':
        region = 'default'

    def output_file_name(_r):
        def get_path(path):
            rep = f'plugins/rcp-be-lol-game-data/global/{_r}/v1/'
            new = path.replace(rep, '')
            return os.path.join(out_dir, _r, 'LCU', os.path.normpath(new))

        return get_path

    wad_sfx_file = os.path.join(data_path, 'default-assets.wad')
    wad_vo_file = os.path.join(data_path, f'{format_region(region)}-assets.wad')
    for cid in get_champions_id():
        sfx.append(f'plugins/rcp-be-lol-game-data/global/default/v1/champion-sfx-audios/{cid}.ogg')
        vo.extend([f'plugins/rcp-be-lol-game-data/global/{region}/v1/champion-choose-vo/{cid}.ogg',
                   f'plugins/rcp-be-lol-game-data/global/{region}/v1/champion-ban-vo/{cid}.ogg'])

    WAD(wad_sfx_file).extract(sfx, out_dir=output_file_name('default'))
    WAD(wad_vo_file).extract(vo, out_dir=output_file_name(region))


def get_game_audio(game_path, out_dir, vgmstream_cli, region='zh_cn', audio_format='wav', max_works=None):
    """
    获取游戏内音频资源
    :param game_path: 游戏目录
    :param out_dir: 输出目录
    :param vgmstream_cli: 转码所需工具路径
    :param region: 地区
    :param audio_format: 音频转码格式
    :param max_works: 最大进程数
    :return:
    """
    with ProcessPoolExecutor(max_workers=max_works) as e:
        fs = dict()
        for root, dirs, files in os.walk(E2A_HASH_PATH):
            # if 'SFX' in root:
            #     continue
            for file in files:
                ext = os.path.splitext(file)[-1]
                if ext == '.json':
                    with open(os.path.join(root, file), encoding='utf-8') as f:
                        data = json.load(f)
                        _type = data['info']['type']
                        kind = data['info']['kind']
                        name = data['info']['name']
                        detail = data['info']['detail']
                        wad_file = os.path.join(game_path, os.path.normpath(data['info']['wad']))
                        audio_raws = WAD(wad_file).extract(list(data['data'].keys()), raw=True)
                        for raw in audio_raws:
                            if raw:
                                audio_files = get_audio_files(raw)
                                del raw
                                for i in audio_files:
                                    thisname = i.filename if i.filename else f'{i.id}.wem'
                                    filename = os.path.join(
                                        out_dir, region if _type == 'VO' else 'default',
                                        _type, kind, name, detail,
                                        thisname.replace('wem', audio_format)
                                    )
                                    makedirs(os.path.dirname(filename))
                                    # i.static_save_file(i.data, filename, False, vgmstream_cli)
                                    fs[e.submit(i.static_save_file, i.data, filename, False, vgmstream_cli)] = (
                                        _type, kind, name, detail, wad_file)

        for f in as_completed(fs):
            try:
                f.result()
            except Exception as exc:
                log.warning(f'generated an exception: {exc}, {fs[f]}')
            else:
                # log.info(f'Done. {fs[f]}')
                pass


@check_time
def main(game_path, out_dir, vgmstream_cli, region='zh_cn', audio_format='wav', max_works=None):
    """
    获取游戏内 音频文件
    :param game_path: 游戏根目录
    :param out_dir: 输出目录
    :param vgmstream_cli: 转码工具
    :param region: 提取的区域与语言, 默认zh_cn
    :param audio_format: 音频格式
    :param max_works: 最大线程数
    :return:
    """
    champion_path = os.path.join(game_path, 'Game', 'DATA', 'FINAL', 'Champions')
    common_path = os.path.join(game_path, 'Game', 'DATA', 'FINAL', 'Maps', 'Shipping')
    lcu_data_path = os.path.join(game_path, 'LeagueClient', 'Plugins', 'rcp-be-lol-game-data')

    update_data_by_local(game_path, region)

    # 获取哈希表
    get_event_audio_hash_table(champion_path, common_path, region, True)

    get_lcu_audio(lcu_data_path, out_dir, region)
    get_game_audio(game_path, out_dir, vgmstream_cli, region, audio_format, max_works)


def get_champion_audio_by_json(json_path, game_path, out_dir, vgmstream_cli, audio_format='wav', max_works=None):
    """
    根据get_event_audio_hash_table生成的哈希表来获取单个英雄的语音
    https://cdn.jsdelivr.net/gh/Virace/lol-audio-events-hashtable@main/
    :param json_path: 哈希表json路径/网址
    :param game_path: 游戏路径
    :param out_dir: 输出目录
    :param vgmstream_cli: 转码工具路径
    :param audio_format: 音频格式
    :param max_works: 最大线程数
    :return:
    """
    if ':' in json_path:
        hash_table = requests.get(json_path).json()
    else:
        with open(json_path, encoding='utf-8') as f:
            hash_table = json.load(f)

    wad_file = os.path.join(game_path, hash_table['info']['wad'])
    with ProcessPoolExecutor(max_workers=max_works) as e:
        fs = dict()
        for file_path, events in hash_table['data'].items():
            audio_raws = WAD(wad_file).extract([file_path], raw=True)
            for raw in audio_raws:
                if raw:
                    audio_files = get_audio_files(raw, hash_table=list(itertools.chain(*events.values())))
                    del raw
                    for event, _hash_table in events.items():
                        for i in audio_files:
                            if i.id in _hash_table:
                                thisname = i.filename if i.filename else f'{i.id}.wem'
                                filename = os.path.join(
                                    out_dir,
                                    event,
                                    thisname.replace('wem', audio_format)
                                )
                                makedirs(os.path.dirname(filename))
                                fs[e.submit(i.static_save_file, i.data, filename, False, vgmstream_cli)] = (
                                    event, i.id, wad_file)

        for f in as_completed(fs):
            try:
                f.result()
            except Exception as exc:
                log.warning(f'generated an exception: {exc}, {fs[f]}')
            else:
                # log.info(f'Done. {fs[f]}')
                pass


def check_game_version(game_path):
    """
    检查游戏版本文件, 用来判断是否更新资源
    :param game_path:
    :return:
    """
    old_version = ''
    if os.path.exists(LOCAL_VERSION_FILE):
        with open(LOCAL_VERSION_FILE, encoding='utf-8') as f:
            old_version = f.read()
    new_version = get_game_version_by_local(game_path)
    if old_version == new_version:
        return False
    else:
        with open(LOCAL_VERSION_FILE, 'w+', encoding='utf-8') as f:
            f.write(new_version)
        return True


