# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: PyCharm
# @Create  : 2021/2/25 1:40
# @Update  : 2021/3/16 20:14
# @Detail  : 

import os


CHAMPIONS_PATH = os.path.join(os.path.dirname(__file__), '%s')
CHAMPIONS_SUMMARY = os.path.join(CHAMPIONS_PATH, 'champion-summary.json')
CHAMPIONS_SKINS = os.path.join(CHAMPIONS_PATH, 'skins.json')
CHAMPIONS_DETAILED_PATH = os.path.join(CHAMPIONS_PATH, 'champions')

# if not os.path.exists(CHAMPIONS_DETAILED_PATH):
#     os.mkdir(CHAMPIONS_DETAILED_PATH)

__all__ = [CHAMPIONS_SKINS, CHAMPIONS_SUMMARY, CHAMPIONS_DETAILED_PATH, CHAMPIONS_PATH]

