# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: PyCharm
# @Create  : 2021/2/24 23:41
# @Update  : 2021/3/15 22:53
# @Detail  : 

import os
from collections import defaultdict


def str_get_number(s):
    i = [*filter(str.isdigit, s)]
    if i:
        return int(''.join([*i]))


def tree():
    return defaultdict(tree)


def makedirs(path):
    try:
        if not os.path.exists(path):
            os.makedirs(path)
    except FileExistsError as _:
        pass
