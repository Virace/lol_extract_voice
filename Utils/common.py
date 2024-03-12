# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2022/8/16 0:15
# @Update  : 2024/3/12 13:03
# @Detail  : 通用函数

import json
import os
import re
import shutil
import time
import requests
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
        if clear and os.path.exists(path):
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


def dump_json(obj, path, ensure_ascii=False, cls=None):
    """
    将对象写入json文件
    :param obj: 对象
    :param path: 路径
    :param ensure_ascii: 是否转义
    :param cls: 类
    :return:
    """
    with open(path, 'w+', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=ensure_ascii, cls=cls)


def load_json(path):
    """
    读取json文件
    :param path:
    :return:
    """

    # 如果文件不存在这返回空字典
    if not os.path.exists(path):
        return {}

    # 如果报错则返回空字典
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f'文件报错， 位置: {path}, 错误: {e}')
        return {}
    # with open(path, encoding='utf-8') as f:
    #     return json.load(f)


def list2dict(data, key):
    """
    将类似[{'id':1, 'xx':xx}, ...]的列表转换为字典
    :param data:
    :param key:
    :return:
    """
    return {item[key]: item for item in data}


def download_file(url, path):
    """
    下载文件
    :param url: 下载链接
    :param path: 保存路径
    :return:
    """
    r = requests.get(url, stream=True)
    with open(path, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)
                f.flush()
    return path


def replace(data, repl):
    """
    替换
    :param data:
    :param repl:键值对
    :return:
    """
    for key, value in repl.items():
        data = data.replace(key, value)
    return data


def re_replace(data, repl):
    """
    正则替换
    :param data:
    :param repl: 键值对
    :return:
    """

    def replf(v):
        def temp(mobj):
            match = mobj.groups()[0]
            if match:
                return v.format(match)
            else:
                return v.replace('{}', '')

        return temp

    for key, value in repl.items():
        if '{}' in value:
            value = replf(value)
        data = re.compile(f'{key}', re.I).sub(value, data)
    return data
