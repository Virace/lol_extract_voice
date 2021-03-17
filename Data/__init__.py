# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: PyCharm
# @Create  : 2021/2/25 1:40
# @Update  : 2021/3/17 14:2
# @Detail  : 

import os

DATA_PATH = os.path.join(os.path.dirname(__file__), '%s')
DATA_SUMMARY = os.path.join(DATA_PATH, 'champion-summary.json')
DATA_SKINS = os.path.join(DATA_PATH, 'skins.json')
DATA_CHAMPIONS_PATH = os.path.join(DATA_PATH, 'champions')
DATA_MAPS = os.path.join(DATA_PATH, 'maps.json')

__all__ = [DATA_SKINS, DATA_SUMMARY, DATA_CHAMPIONS_PATH, DATA_PATH, DATA_MAPS]

