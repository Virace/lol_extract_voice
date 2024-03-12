# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2022/8/26 14:00
# @Update  : 2024/3/12 14:21
# @Detail  : config.py

import os

from dotenv import load_dotenv

from Utils.type_hints import StrPath

# 游戏目录
GAME_PATH: StrPath = ''

# 输出目录
OUTPUT_PATH: StrPath = ''

# 要处理的区域文件
GAME_REGION: str = 'zh_CN'

# 排除处理的类型 (VO/SFX/MUSIC) 台词音频/效果音频/背景音乐
EXCLUDE_TYPE: list = ['SFX']

# vgmstream cli程序, 用来转码, 如果不提供则默认输出为wem格式。
VGMSTREAM_PATH: str = ''

######################################################
#                ！！！！！！！！！！                #
#                以下配置无需手动修改                #
#                ！！！！！！！！！！                #
######################################################

# 从环境变量中获取 ENV_ONLY，默认为 False
ENV_ONLY: bool = os.getenv('LOL_ENV_ONLY', '0').lower() not in ['0', 'false']

# 从环境变量中获取 ENV_PATH，默认为 .lol.env
ENV_PATH: StrPath = os.getenv('LOL_ENV_PATH', '.lol.env')

# 是否使用ENV_PATH中的配置覆盖环境变量中的配置，默认为 False
ENV_OVERRIDE: bool = os.getenv('LOL_ENV_OVERRIDE', '0').lower() not in ['0', 'false']

# 设置需要获取的参数列表
params = ['GAME_PATH', 'GAME_REGION', 'OUTPUT_PATH', 'EXCLUDE_TYPE', 'VGMSTREAM_PATH']

# 根据 ENV_ONLY 的值选择获取参数的方式
if ENV_ONLY:

    # 从.lol.env文件中获取参数
    load_dotenv(dotenv_path=ENV_PATH, override=ENV_OVERRIDE)

    # 如果 ENV_ONLY 为 True，则所有参数都从环境变量中获取
    for param in params:
        if param == 'EXCLUDE_TYPE':
            globals()[param] = os.getenv(f'LOL_{param}', '').split(',')
        else:
            globals()[param] = os.getenv(f'LOL_{param}', '')
else:
    # 否则，优先使用上面常量，如果为 None，则从环境变量中获取
    for param in params:
        globals()[param] = globals()[param] or os.getenv(f'LOL_{param}')

# 如果GAME_PATH 或 OUTPUT_PATH 为空则抛出异常
if not GAME_PATH:
    raise ValueError('GAME_PATH不能为空')

if not OUTPUT_PATH:
    raise ValueError('OUTPUT_PATH不能为空')

# 音频目录, 最终解包生成的音频文件都放在这
AUDIO_PATH = os.path.join(OUTPUT_PATH, 'audios')

# 缓存目录, 解包生成的一些文件会放在这里, 可以删除
TEMP_PATH = os.path.join(OUTPUT_PATH, 'temps')

# 日志目录, 一些文件解析错误不会关闭程序而是记录在日志中
LOG_PATH = os.path.join(OUTPUT_PATH, 'logs')

# 哈希目录, 存放所有与 k,v 相关数据
HASH_PATH = os.path.join(OUTPUT_PATH, 'hashes')

# 有关于游戏内的数据文件
MANIFEST_PATH = os.path.join(OUTPUT_PATH, 'manifest')

# 游戏版本文件, 用来记录当前解包文件的版本
LOCAL_VERSION_FILE = os.path.join(OUTPUT_PATH, 'game_version')

# 游戏英雄文件目录 (Game/DATA/FINAL/Champions)
GAME_CHAMPION_PATH = os.path.join(GAME_PATH, 'Game', 'DATA', 'FINAL', 'Champions')

# 游戏地图(公共)文件目录 (Game/DATA/FINAL/Maps/Shipping)
GAME_MAPS_PATH = os.path.join(GAME_PATH, 'Game', 'DATA', 'FINAL', 'Maps', 'Shipping')

# 游戏大厅资源目录
GAME_LCU_PATH = os.path.join(GAME_PATH, 'LeagueClient', 'Plugins', 'rcp-be-lol-game-data')

# 修正
if GAME_REGION.lower() == 'en_us':
    GAME_REGION = 'default'
