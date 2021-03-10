# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: PyCharm
# @Create  : 2021/3/4 22:11
# @Update  : 2021/3/4 23:18
# @Detail  : 

import os

GAME = os.path.join(os.path.dirname(__file__), 'hashes.game.txt')
LCU = os.path.join(os.path.dirname(__file__), 'hashes.lcu.txt')

__all__ = [
    'GAME',
    'LCU'
]
