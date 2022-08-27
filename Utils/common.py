# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2022/8/16 0:15
# @Update  : 2022/8/26 20:27
# @Detail  : 通用函数

import os
import shutil
import time
from collections import defaultdict

from loguru import logger


def str_get_number(s):
    """
    从字符串中提取数字
    :param s:
    :return:
    """
    i = [*filter(str.isdigit, s)]
    if i:
        return int(''.join([*i]))


def tree():
    """
    defaultdict 创建一个带默认值的dict，默认值为自身
    :return:
    """
    return defaultdict(tree)


def makedirs(path, clear=False):
    """
    如果文件夹不存在，则使用os.makedirs创建文件，存在则不处理
    :param path: 路径
    :param clear: 是否清空文件夹，创建前直接清空文件夹
    :return:
    """
    try:
        if clear:
            shutil.rmtree(path)
        if not os.path.exists(path):
            os.makedirs(path)
    except FileExistsError as _:
        pass


def format_region(region):
    """
    格式化地区名称zh_CN
    :param region:
    :return:
    """
    return region[:3].lower() + region[3:].upper()


def de_duplication(a1, b1):
    """
    去重, 数组套元组, 按元组内的元素去重
    :param a1: 对照组
    :param b1: 待去重数组
    :return:
    """

    class Stop(Exception):
        pass

    b2 = []
    for item in b1:
        try:
            for i in item:
                if i not in a1:
                    a1.update(item)
                    b2.append(item)
                    raise Stop
        except Stop:
            continue

    return a1, set(b2)


def check_time(func):
    """
    获取函数执行时间
    :param func:
    :return:
    """

    def wrapper(*args, **kwargs):
        st = time.time()
        ret = func(*args, **kwargs)
        logger.info(f'Func: {func.__module__}.{func.__name__}, Time Spent: {round(time.time() - st, 2)}')
        return ret

    return wrapper
