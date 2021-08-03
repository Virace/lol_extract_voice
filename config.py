# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: PyCharm
# @Create  : 2021/5/6 2:09
# @Update  : 2021/8/3 16:30
# @Detail  : 配置文件

import os

BASE_PATH = os.path.dirname(__file__)
TEMP_PATH = os.path.join(BASE_PATH, 'Temp')

if not os.path.exists(TEMP_PATH):
    os.mkdir(TEMP_PATH)
# 用来检测本地游戏版本
LOCAL_VERSION_FILE = os.path.join(TEMP_PATH, 'game_version')
