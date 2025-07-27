# 🐍 Sparse is better than dense.
# 🐼 稀疏优于稠密
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2024/5/6 1:19
# @Update  : 2025/7/27 23:00
# @Detail  : 通用函数


import json
import os
import re
import shutil
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from json import JSONEncoder
from os import PathLike
from pathlib import Path, PosixPath, WindowsPath

import requests
from loguru import logger

if os.name == "nt":
    BasePath = WindowsPath
else:
    BasePath = PosixPath


def capitalize_first_letter(word):
    if not word:
        return word  # 处理空字符串的情况
    return word[0].upper() + word[1:]


def sanitize_filename(filename: str, replacement: str = "_") -> str:
    """
    清理文件名中的非法字符，使其在Windows等操作系统中安全可用。

    :param filename: 原始文件名或路径片段。
    :param replacement: 用于替换非法字符的字符串，默认为下划线 "_".
    :return: 清理后的安全文件名。
    """
    # Windows 文件名非法字符: < > : " / \ | ? *
    # 同时包括控制字符 (ASCII 0-31)
    illegal_chars_re = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
    return illegal_chars_re.sub(replacement, filename)


class EnhancedPath(BasePath):
    """
    增强Path
    """

    def format(self, **kwargs):
        """
        格式化路径, 就是 str.format
        :param kwargs:
        :return:
        """
        return EnhancedPath(super().__str__().format(**kwargs))


class Singleton(type):
    """
    线程安全的单例元类

    使用方式:
    ```
    class MyClass(metaclass=Singleton):
        pass
    ```
    """

    _instances = {}
    _lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    # super(Singleton, cls)
                    cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


def str_get_number(s, threshold=1000):
    """
    从字符串中提取数字
    :param s: 输入字符串
    :param threshold: 阈值，当字符串长度超过此值时，使用正则表达式提取数字
    :return: 提取的数字
    """
    if len(s) > threshold:
        matches = re.findall(r"\d+", s)
        if matches:
            return int("".join(matches))
    else:
        i = [*filter(lambda x: x.isdigit(), s)]
        if i:
            return int("".join(i))


def tree():
    """
    defaultdict 创建一个带默认值的dict，默认值为自身
    :return:
    """
    return defaultdict(tree)


def makedirs(path: str | PathLike | Path, clear: bool = False):
    """
    如果文件夹不存在，则使用os.makedirs创建文件，存在则不处理
    :param path: 路径
    :param clear: 是否清空文件夹，创建前直接清空文件夹
    :return:
    """

    path = Path(path)

    try:
        if clear and path.exists():
            shutil.rmtree(path)

        if not path.exists():
            path.mkdir(parents=True)

    except FileExistsError as _:
        # 防御性编程
        pass


def format_region(region: str) -> str:
    """
    格式化地区名称zh_CN
    :param region:
    :return:
    """
    if region.lower() == "default":
        return region
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


def check_time(func: callable) -> Callable:
    """
    获取函数执行时间
    :param func:
    :return:
    """

    def wrapper(*args, **kwargs):
        st = time.time()
        ret = func(*args, **kwargs)
        logger.info(f"Func: {func.__module__}.{func.__name__}, Time Spent: {round(time.time() - st, 2)}")
        return ret

    return wrapper


def dump_json(
    obj,
    path: str | PathLike | Path,
    ensure_ascii: bool = False,
    cls: type[JSONEncoder] | None = None,
    indent: int = None,
):
    """
    将对象写入json文件
    :param obj: 对象
    :param path: 路径
    :param ensure_ascii: 是否转义
    :param cls: 类
    :param indent: 缩进级别, None 或 0 表示紧凑输出
    :return:
    """
    path = Path(path)

    with path.open("w+", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=ensure_ascii, cls=cls, indent=indent)


def load_json(path: str | PathLike | Path) -> dict:
    """
    读取json文件
    :param path:
    :return:
    """

    path = Path(path)

    # 如果文件不存在这返回空字典
    if not path.exists():
        return {}

    # 如果报错则返回空字典
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"文件不存在， 位置: {path}")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析错误， 位置: {path}, 错误: {e}")
        return {}
    except Exception as e:
        logger.error(f"未知错误， 位置: {path}, 错误: {e}")
        return {}


def list2dict(data, key):
    """
    将类似[{'id':1, 'xx':xx}, ...]的列表转换为字典
    :param data:
    :param key:
    :return:
    """
    return {item[key]: item for item in data}


def download_file(url: str, path: str | PathLike | Path) -> Path:
    """
    下载文件
    :param url: 下载链接
    :param path: 保存路径
    :return:
    """
    path = Path(path)
    r = requests.get(url, stream=True)
    with open(path, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)
                f.flush()
    return path


def fetch_json_data(
    url: str,
    method: str = "GET",
    retries: int = 5,
    delay: int = 2,
    params: dict = None,
    data: dict = None,
    headers: dict = None,
    callback: callable = None,
) -> dict:
    """
    从给定的URL获取JSON数据

    :param url: 要获取数据的URL。
    :param method: HTTP请求方法 ('GET' 或 'POST')，默认为 'GET'。
    :param retries: 遇到网络错误时的重试次数，默认为5次。
    :param delay: 每次重试之间的延迟时间（秒），默认为2秒。
    :param params: URL中的请求参数（适用于GET请求）。
    :param data: 请求体中的数据（适用于POST请求）。
    :param headers: 请求头信息。
    :param callback: 一个回调函数，用于处理非JSON格式的响应内容。
    :return: 返回JSON格式的数据（字典），或回调函数的处理结果。
    :raises ValueError: 如果响应内容不是JSON格式且未提供回调函数，则抛出异常。
    """
    for attempt in range(retries):
        try:
            logger.trace(f"第 {attempt + 1} 次尝试访问 URL: {url}，总共尝试次数: {retries}")

            if method.upper() == "GET":
                response = requests.get(url, params=params, headers=headers)
            elif method.upper() == "POST":
                response = requests.post(url, params=params, data=data, headers=headers)
            else:
                raise ValueError("无效的请求方法。请使用 'GET' 或 'POST'。")

            logger.trace(f"收到来自 URL: {url} 的响应，状态码为: {response.status_code}")

            try:
                json_data = response.json()
                logger.debug(f"成功从 URL: {url} 解析出JSON数据")
                return json_data
            except ValueError:
                logger.warning(f"来自 URL: {url} 的响应内容不是JSON格式")
                if callback:
                    logger.debug(f"使用回调函数处理来自 URL: {url} 的非JSON响应内容")
                    return callback(response.text)
                else:
                    raise ValueError(f"响应内容不是JSON格式，且未提供回调函数用于处理 URL: {url} 的数据")

        except requests.RequestException as e:
            logger.error(f"网络错误: {e}，将在 {delay} 秒后重试...")
            time.sleep(delay)

    logger.error(f"多次尝试后仍无法从 URL: {url} 获取JSON数据，已达到最大重试次数: {retries}")
    raise ValueError(f"多次尝试后仍无法从 URL: {url} 获取JSON数据，已达到最大重试次数: {retries}")


def replace(data: str, repl: dict[str, str]) -> str:
    """
    替换
    :param data:
    :param repl:键值对
    :return:
    """
    for key, value in repl.items():
        data = data.replace(key, value)
    return data


def re_replace(data: str, repl: dict[str, str]) -> str:
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
                return v.replace("{}", "")

        return temp

    for key, value in repl.items():
        if "{}" in value:
            value = replf(value)
        data = re.compile(f"{key}", re.I).sub(value, data)
    return data
