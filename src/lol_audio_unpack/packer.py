# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: PyCharm
# @Create  : 2021/9/20 17:01
# @Update  : 2024/1/12 4:23
# @Detail  : 用于单独打包英雄台词文件

import subprocess

from Hashes import game_data
import json
import re
import shutil
# import py7zr
import pathlib
import re
import os
from loguru import logger
from concurrent.futures import ProcessPoolExecutor, as_completed
import time
from string import Template

README_CHARS_TPL = '''英雄ID: $id
英雄别名: $alias
英雄名字: $name
包含皮肤: $skins

文件类别: $type
打包版本: $version
打包时间: $time


                                                            Virace
                                                            孤独的未知数
                                                            https://x-item.com
                                                            https://space.bilibili.com/12353537

                                                            禁止倒卖，音频版权为游戏公司所有'''

README_MAPS_TPL = '''包含地图: $maps

打包版本: $version
文件类别: $type
打包时间: $time


                                                            Virace
                                                            孤独的未知数
                                                            https://x-item.com
                                                            https://space.bilibili.com/12353537

                                                            禁止倒卖，音频版权为游戏公司所有'''

SEVENZIP_EXE = r"D:\Programs\Tools\7-Zip\x64\7zz.exe"
SFX_FILE = r"D:/Programs/Tools/7-Zip/x64/7zCon.sfx"


PASSWORD_VO = 'x-item-vo'
PASSWROD_SFX = 'x-item-sfx'
PASSWROD_MUSIC = 'x-item-music'


def get_data():
    hero = {}
    skins = {}
    skinlines = game_data.get_skinlines()
    for _id in game_data.get_champions_id():
        if _id == -1:
            continue
        this = game_data.get_champion_detail_by_id(_id)
        hero.update({str(_id): dict(name=this['name'], title=this['title'], alias=this['alias'])})
        for skin in this['skins']:
            if skin['skinLines'] is not None:
                skinline_name = '-'.join([skinlines[line['id']] for line in skin['skinLines']])
                skin['skinLines'] = skinline_name
            skins.update({str(skin['id']): skin})
            if 'questSkinInfo' in skin and 'tiers' in skin['questSkinInfo']:
                for t in skin['questSkinInfo']['tiers']:
                    skins.update({str(t['id']): t})
    return hero, skins


def create_mark(path):
    """
    创建标记
    :param path:
    :return:
    """
    pathlib.Path(path, 'x-item').touch()
    pathlib.Path(path, 'x-item-禁止倒卖').touch()


def create_readme(path, version, param, text_tpl=README_CHARS_TPL):
    tpl = Template(text_tpl)
    text = tpl.substitute(**param, version=version,
                          time=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
    with open(os.path.join(path, '说明文档.txt'), 'w+', encoding='utf-8') as f:
        f.write(text)


def files_rename(_l):
    """
    文件批量重命名
    :param _l: [(src, dst), ...]
    :return:
    """
    for src, dst in _l:
        file_rename(src, dst)
        logger.debug(f'RENAME: {src}, {dst}')

def file_rename(src, dst, dot=True):
    # 文件重命名，点模式来判断文件是否已经改过名了
    if dot and '·' in src:
        return

    os.rename(src, dst)


def seven_zip_pack(src, zipfile, password, exe=SEVENZIP_EXE, sfx=False):
    # & 'C:\Program Files\7-Zip\7z.exe' a .\maps.7z .\maps -mx9 -ms=16g -mhe=on -mmt=16 -p123456
    if sfx:
        zipfile = os.path.splitext(zipfile)[0] + '.exe'

    command = [exe, 'a', f'{zipfile}', f'{src}', '-mx9', '-ms=16g', '-mhe=on', '-mmt=16', f'-p{password}']

    if sfx:
        command.append(f'-sfx7zCon.sfx')

    subprocess.run(command, cwd=os.path.dirname(exe))


def create_7zip(src, zipfile, arcname=None, password=None):
    """
    创建压缩包
    :param src: 源
    :param zipfile: 压缩包
    :param arcname: 压缩包内根目录名
    :param password: 密码
    :return:
    """
    if arcname is None:
        arcname = os.path.basename(src)
    if src[-1] == '/' or src[-1] == '\\':
        arcname = os.path.dirname(src)
    if not os.path.exists(os.path.dirname(zipfile)):
        os.makedirs(os.path.dirname(zipfile))
    with py7zr.SevenZipFile(zipfile, 'w', password=password, header_encryption=password is not None) as archive:
        archive.writeall(src, arcname)


def or_dir(path):
    """
    整理目录, 对于地图目录会有多余一层文件夹
    传入的要是需要处理的根目录
    :return:
    """
    # 移动目录
    for root, dirs, files in os.walk(path):
        for file in files:
            dst = os.path.dirname(root)
            if dst != path:
                shutil.move(os.path.join(root, file), os.path.dirname(root))
    # 创建mark，删除空文件夹
    for root, dirs, files in os.walk(path):
        for _dir in dirs:
            this = os.path.join(root, _dir)
            if os.listdir(this):
                create_mark(this)
            else:
                os.rmdir(this)


def pick_vo_c(src_path, version, dst_path):
    TARGET_PATH = os.path.join(src_path, 'zh_cn')
    BAN_PATH = os.path.join(TARGET_PATH, 'LCU', 'champion-ban-vo')
    CHOOSE_PATH = os.path.join(TARGET_PATH, 'LCU', 'champion-choose-vo')
    ACTERS_PATH = os.path.join(TARGET_PATH, 'VO', 'characters')

    HREO_LIBRARY, SKINS_LIBRARY = get_data()

    rename_list = []
    for hero_id, item in HREO_LIBRARY.items():
        alias = item['alias']
        name = f'{alias}·{item["name"]}·{item["title"]}·ID{hero_id}'
        p = os.path.join(ACTERS_PATH, alias.lower())
        dst = os.path.join(ACTERS_PATH, name)
        if not os.path.exists(p):
            logger.warning(f'PASS: {item}')
            continue
        skins = []
        for skin in os.listdir(p):
            # short id
            skin_sid = skin.replace('skin', '')
            skin_id = f'{hero_id}{skin_sid.zfill(3)}'
            if skin_sid == '0':
                skin_name = '默认皮肤'
                skins.append(skin_name)
            elif skin_id in SKINS_LIBRARY:
                this_skin = SKINS_LIBRARY[skin_id]
                skin_name = this_skin['name']
                skins.append(skin_name)
                skin_name = re.compile(r'[<>/|:"*?“”\'\\]').sub(' ', skin_name).replace(' · ', '·')
                skin_name = skin_name.replace(item["title"], '').strip()
                skin_name = skin_name.replace('  ', ' ').replace(' ', '·')
                # if 'skinLines' in this_skin and this_skin['skinLines'] is not None:
                #     skin_name += f'[{this_skin["skinLines"]}]'
            else:
                logger.warning(f'Not found: {skin_id}')
                continue

            skin_name = f'{skin_id}·{skin_name}'

            # 在文件夹内创建mark文件
            create_mark(os.path.join(p, skin))

            # 更改皮肤文件夹名字
            rename_list.append((os.path.join(p, skin), os.path.join(p, skin_name)))
            # os.rename(os.path.join(p, skin), os.path.join(p, skin_name))
            # logger.debug(f'RENAME: {os.path.join(p, skin)}, {os.path.join(p, skin_name)}')
            # print(name, skin_name)

        # 复制ban、pick文件
        shutil.copyfile(os.path.join(CHOOSE_PATH, f'{hero_id}.ogg'), os.path.join(p, f'{alias}·选取(choose).mp3'))
        shutil.copyfile(os.path.join(BAN_PATH, f'{hero_id}.ogg'), os.path.join(p, f'{alias}·禁用(ban).mp3'))

        # 创建readme
        create_mark(p)
        create_readme(p, version,
                      dict(id=hero_id, alias=alias, name=f'{item["name"]}·{item["title"]}', skins='、'.join(skins),
                           type='台词'))

        # 更改英雄文件夹名字
        rename_list.append((p, dst))
    files_rename(rename_list)
    # 打包压缩文件
    tp = os.path.join(dst_path, 'VO', 'Characters')

    with ProcessPoolExecutor(max_workers=12) as e:
        fs = {}
        for item in os.listdir(ACTERS_PATH):
            src = os.path.join(ACTERS_PATH, item)
            archive = os.path.join(tp, f'{item}-{version}-VO.exe')
            if os.path.exists(archive):
                logger.info(f'Exists zip. {archive}')
                continue
            fs.update({e.submit(seven_zip_pack, src, archive, password=PASSWORD_VO, sfx=True): item})
            # create_7zip(os.path.join(tp, item), os.path.join(tp, f'{item}.7z'), password=PASSWORD_VO)

        for f in as_completed(fs):
            try:
                f.result()
            except Exception as exc:
                logger.warning(f'generated an exception: {exc}, {fs[f]}')
            else:
                logger.info(f'Create zip. {os.path.join(tp, f"{fs[f]}.7z")}')


def pick_sfx_c(src_path, version, dst_path):
    TARGET_PATH = os.path.join(src_path, 'default')
    SFX_PATH = os.path.join(TARGET_PATH, 'LCU', 'champion-sfx-audios')
    ACTERS_PATH = os.path.join(TARGET_PATH, 'SFX', 'characters')

    HREO_LIBRARY, SKINS_LIBRARY = get_data()

    rename_list = []
    for hero_id, item in HREO_LIBRARY.items():
        alias = item['alias']
        name = f'{alias}·{item["name"]}·{item["title"]}·ID{hero_id}'
        p = os.path.join(ACTERS_PATH, alias.lower())
        dst = os.path.join(ACTERS_PATH, name)
        if not os.path.exists(p):
            logger.warning(f'PASS: {item}')
            continue

        # 处理皮肤
        skins = []
        for skin in os.listdir(p):
            # short id
            skin_sid = skin.replace('skin', '')
            skin_id = f'{hero_id}{skin_sid.zfill(3)}'
            if skin_sid == '0':
                skin_name = '默认皮肤'
                skins.append(skin_name)
            elif skin_id in SKINS_LIBRARY:
                this_skin = SKINS_LIBRARY[skin_id]
                skin_name = this_skin['name']
                skins.append(skin_name)
                skin_name = re.compile(r'[<>/|:"*?“”\'\\]').sub(' ', skin_name).replace(' · ', '·')
                skin_name = skin_name.replace(item["title"], '').strip()
                skin_name = skin_name.replace('  ', ' ').replace(' ', '·')
                # if 'skinLines' in this_skin and this_skin['skinLines'] is not None:
                #     skin_name += f'[{this_skin["skinLines"]}]'
            else:
                logger.warning(f'Not found: {skin_id}')
                continue

            skin_name = f'{skin_id}·{skin_name}'

            # 在文件夹内创建mark文件
            create_mark(os.path.join(p, skin))

            # 更改皮肤文件夹名字
            rename_list.append((os.path.join(p, skin), os.path.join(p, skin_name)))
            # os.rename(os.path.join(p, skin), os.path.join(p, skin_name))
            # logger.debug(f'RENAME: {os.path.join(p, skin)}, {os.path.join(p, skin_name)}')
            # print(name, skin_name)

        # 复制ban、pick文件
        shutil.copyfile(os.path.join(SFX_PATH, f'{hero_id}.ogg'), os.path.join(p, f'{alias}·效果音(sfx).ogg'))

        # 创建readme
        create_mark(p)
        create_readme(p, version,
                      dict(id=hero_id, alias=alias, name=f'{item["name"]}·{item["title"]}', skins='、'.join(skins),
                           type='音效'))

        # 更改英雄文件夹名字
        rename_list.append((p, dst))
    files_rename(rename_list)

    create_mark(ACTERS_PATH)
    create_readme(ACTERS_PATH, version,
                  dict(id=0, alias='ALL', name=f'全部英雄', skins='全部皮肤',
                       type='音效'))
    # 打包压缩文件
    # tp = os.path.join(dst_path, 'SFX', f'Characters·英雄效果音-{version}-SFX.7z')

    # seven_zip_pack(ACTERS_PATH, tp, password=PASSWROD_SFX)
    tp = os.path.join(dst_path, 'SFX', 'Characters')

    with ProcessPoolExecutor(max_workers=3) as e:
        fs = {}
        for item in os.listdir(ACTERS_PATH):
            src = os.path.join(ACTERS_PATH, item)
            archive = os.path.join(tp, f'{item}-{version}-SFX.7z')
            fs.update({e.submit(seven_zip_pack, src, archive, password=PASSWROD_SFX, sfx=True): item})
            # create_7zip(os.path.join(tp, item), os.path.join(tp, f'{item}.7z'), password=PASSWORD_VO)

        for f in as_completed(fs):
            try:
                f.result()
            except Exception as exc:
                logger.warning(f'generated an exception: {exc}, {fs[f]}')
            else:
                logger.info(f'Create zip. {os.path.join(tp, f"{fs[f]}.7z")}')


def pick_sfx_m(src_path, version, dst_path):
    pass

def pick_m(src_path, version, dst_path):
    # f'Characters·英雄效果音-{version}-SFX.7z'
    temp = [
        (os.path.join(src_path, 'zh_cn', 'VO', 'maps'), os.path.join(dst_path, 'VO', f'Maps·地图NPC台词-{version}-VO.7z'),
         PASSWORD_VO, 'NPC台词'),
        (os.path.join(src_path, 'default', 'SFX', 'maps'), os.path.join(dst_path, 'SFX', f'Maps·地图音效-{version}-SFX.7z'),
         PASSWROD_SFX, '音效'),
        # (
        #     os.path.join(src_path, 'default', 'MUSIC', 'maps'),
        #     os.path.join(dst_path, 'MUSIC', f'Maps·地图背景音乐-{version}-MUSIC.7z'),
        #     PASSWROD_MUSIC, '背景音乐'),
    ]

    MAP_LIBRARY = {item['id']: item['name'] for item in game_data.get_maps()}
    for path in temp:
        or_dir(path[0])

        maps = []
        for item in os.listdir(path[0]):
            reg = re.compile(r'map(\d+)').findall(item)
            if reg:
                mid = int(reg[0])
            else:
                mid = 0
            maps.append(MAP_LIBRARY[mid])
            name = f'{MAP_LIBRARY[mid]}·ID{mid}'
            os.rename(os.path.join(path[0], item), os.path.join(path[0], name))
            logger.debug(f'RENAME: {os.path.join(path[0], item)}, {os.path.join(path[0], name)}')
        create_mark(path[0])
        create_readme(path[0], version, dict(maps='、'.join(maps), type=path[3]), README_MAPS_TPL)
        logger.info(f"Create zip. {path[1]}")
        seven_zip_pack(path[0], path[1], password=path[2], sfx=True)


if __name__ == '__main__':
    pick_vo_c(r'E:\Caches\League of legends Res\audio\audios', '14.1', r'E:\Caches\LoL\Pack')
    # seven_zip_pack(r"D:\Programs\Tools\7-Zip\x64\x64", r"D:\Programs\Tools\7-Zip\x64\test1.exe", '123456', sfx=True)



