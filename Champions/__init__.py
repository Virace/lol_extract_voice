# -*- coding: utf-8 -*-
# @Time    : 2021/2/25 1:40
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: PyCharm
# @Detail  :

import os

CHAMPIONS_PATH = os.path.dirname(__file__)
CHAMPIONS_SUMMARY = os.path.join(CHAMPIONS_PATH, 'champion-summary.json')
CHAMPIONS_SKINS = os.path.join(CHAMPIONS_PATH, 'skins.json')
CHAMPIONS_DETAILED_PATH = os.path.join(CHAMPIONS_PATH, 'champions')

if not os.path.exists(CHAMPIONS_DETAILED_PATH):
    os.mkdir(CHAMPIONS_DETAILED_PATH)

__all__ = [CHAMPIONS_SKINS, CHAMPIONS_SUMMARY, CHAMPIONS_DETAILED_PATH, CHAMPIONS_PATH]
