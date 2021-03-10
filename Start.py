# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : https://x-item.com
# @Software: Pycharm
# @Create  : 2020/05/19日 14点58分
# @Update  : 2021/3/4 21:13
# @Detail  : 


import os
from concurrent.futures import ThreadPoolExecutor

import Config as config

from cdragontoolbox.wad import Wad
from cdragontoolbox.hashes import default_hashfile


def wad_extract(filename, output=None):
    """
    WAD文件解包
    :param filename: 输入文件名
    :param output: 输出目录名
    :return:
    """
    if not output:
        output = os.path.splitext(filename)[0]
    if not os.path.exists(output):
        os.mkdir(output)
    hashfile = default_hashfile(filename)
    wad = Wad(filename, hashes=hashfile.load())
    wad.guess_extensions()
    wad.extract(output, overwrite=True)


def voice_extract(filename, output):
    """
    语音类文件解包(不准确)
    :param filename: 输入文件名
    :param output: 输出目录名
    :return:
    """
    # 如果不想看到输出, 可以使用其他方式调用
    os.system('%s %s %s /soundformat:wav' % (config.REC_CLI, filename, output))


def get_name(name, chinese=True):
    """
    根据游戏数据获取中文名称
    :param name:
    :param chinese:
    :return:
    """
    for item in config.CHAMPION_INFO:
        if item['alias'].lower() == name.lower():
            if chinese:
                return item['name']
            else:
                return item['alias']
        else:
            return name


champion_path = os.path.join(config.GAME_PATH, 'Game', 'DATA', 'FINAL', 'Champions')
common_path = os.path.join(config.GAME_PATH, 'Game', 'DATA', 'FINAL', 'Maps', 'Shipping')

# 获取所有英雄文件名, 筛选设置中对应的国家, 并排除SG文件
champion_list = [item for item in os.listdir(champion_path)
                 if item.lower().find(config.REGION) > 0 and item.lower().find('sg_')]

# 获取公共部分文件名, 筛选设置中对应的国家, 并添加几个公共文件, 排除LEVELS文件因为不包含语音文件
common_list = [item for item in os.listdir(common_path)
               if item.lower().find(config.REGION) > 0 or (item.find('_') < 0 and item.find('LEVELS') < 0)]

# 划分WAD解包临时目录
temp_path = os.path.join(config.OUT_PATH, 'Temps')
if not os.path.exists(temp_path):
    os.mkdir(temp_path)

# 划分WAV文件目录
res_path = os.path.join(config.OUT_PATH, 'Res')
if not os.path.exists(res_path):
    os.mkdir(res_path)

# 为了使用多线程更方便, 生成了一个参数数组[(解包文件1, 解包路径1), ......]
# 其实可以展开写, 按自己习惯
all_wad = [*[(os.path.join(champion_path, item), os.path.join(temp_path, item)) for item in champion_list],
           *[(os.path.join(common_path, item), os.path.join(temp_path, item)) for item in common_list]]

# 并发解包wad, 这一环节吃内存写入和硬盘读取, 修改max_workers调整并发数
with ThreadPoolExecutor(max_workers=3) as executor:
    future = {executor.submit(wad_extract, item[0], item[1]): item for item in all_wad}

# 并发处理wav, 这一环节吃CPU和硬盘写入, U不好的量力而行, 修改max_workers调整并发数
with ThreadPoolExecutor(max_workers=3) as executor:
    for top, dirs, files in os.walk(temp_path):
        for item in files:
            if os.path.splitext(item)[1] in ['.bnk', '.wpk']:
                champion_name = item.split('_')[0]
                skin = os.path.basename(top)
                out_path = os.path.join(res_path, get_name(champion_name), skin)
                executor.submit(voice_extract, os.path.join(top, item), out_path)

# 最后删除临时文件夹
os.system('rd /q /s %s' % temp_path)


# 这次提取只包括英雄语音, 以及地图中的公共语音.
# 如果想提取游戏内全部有关声音的音频文件
# 可以修改63~72行, 使用os.walk来遍历所有游戏内WAD文件然后解包

# 代码没有完全的"绝对"
