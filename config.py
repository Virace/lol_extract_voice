# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2022/8/26 14:00
# @Update  : 2022/8/27 13:12
# @Detail  : 描述

import os

# 游戏目录
GAME_PATH = r''

# 输出目录
OUT_PATH = r''

# 要处理的语言
GAME_REGION = 'zh_CN'

# 排除处理的类型 (VO/SFX/MUSIC) 台词音频/效果音频/背景音乐
EXCLUDE_TYPE = ['SFX']

# vgmstream cli程序, 用来转码, 如果不提供则默认输出为wem格式。
VGMSTREAM_PATH = ''

######################################################
#                ！！！！！！！！！！                #
#                以下配置无需手动修改                #
#                ！！！！！！！！！！                #
######################################################

# 音频目录, 最终解包生成的音频文件都放在这
AUDIO_PATH = os.path.join(OUT_PATH, 'audios')

# 缓存目录, 解包生成的一些文件会放在这里, 可以删除
TEMP_PATH = os.path.join(OUT_PATH, 'temps')

# 日志目录, 一些文件解析错误不会关闭程序而是记录在日志中
LOG_PATH = os.path.join(OUT_PATH, 'logs')

# 哈希目录, 存放所有与 k,v 相关数据
HASH_PATH = os.path.join(OUT_PATH, 'hashes')

# 有关于游戏内的数据文件
MANIFEST_PATH = os.path.join(OUT_PATH, 'manifest')

# 游戏版本文件, 用来记录当前解包文件的版本
LOCAL_VERSION_FILE = os.path.join(OUT_PATH, 'game_version')

# 游戏英雄文件目录 (Game/DATA/FINAL/Champions)
GAME_CHAMPION_PATH = os.path.join(GAME_PATH, 'Game', 'DATA', 'FINAL', 'Champions')

# 游戏地图(公共)文件目录 (Game/DATA/FINAL/Maps/Shipping)
GAME_MAPS_PATH = os.path.join(GAME_PATH, 'Game', 'DATA', 'FINAL', 'Maps', 'Shipping')

# 游戏大厅资源目录
GAME_LCU_PATH = os.path.join(GAME_PATH, 'LeagueClient', 'Plugins', 'rcp-be-lol-game-data')

# 修正
if GAME_REGION.lower() == 'en_us':
    GAME_REGION = 'default'
