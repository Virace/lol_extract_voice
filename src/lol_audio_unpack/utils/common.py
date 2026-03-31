"""通用文件读写、路径处理与杂项辅助函数。"""
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

import msgpack
from loguru import logger
from ruamel.yaml import YAML

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
    cleaned = illegal_chars_re.sub(replacement, filename)

    # Windows 不允许文件名以空格或点结尾
    cleaned = cleaned.rstrip(" .")

    # 如果清理后为空，使用默认名称
    return cleaned if cleaned else "unnamed"


def format_duration(duration_ms: float) -> str:
    """
    格式化时间显示，自动选择最合适的单位

    单位转换阈值采用1.5倍关系：
    - < 1500ms: 显示为毫秒 (如: 800ms)
    - >= 1500ms 且 < 90s: 显示为秒+毫秒 (如: 1.5s (1500ms))
    - >= 90s 且 < 5400s(90min): 显示为分+秒 (如: 1.5min (90s))
    - >= 5400s: 显示为时+分 (如: 1.5h (90min))

    :param duration_ms: 耗时（毫秒）
    :returns: 格式化后的时间字符串
    """
    # 转换阈值（1.5倍关系）
    MS_TO_S_THRESHOLD = 1500  # 1.5秒
    S_TO_MIN_THRESHOLD = 90  # 1.5分钟
    MIN_TO_H_THRESHOLD = 90  # 1.5小时

    if duration_ms < MS_TO_S_THRESHOLD:
        # 小于1.5秒，只显示毫秒
        return f"{duration_ms:.0f}ms"

    duration_s = duration_ms / 1000
    if duration_s < S_TO_MIN_THRESHOLD:
        # 小于1.5分钟，显示秒+毫秒
        return f"{duration_s:.1f}s ({duration_ms:.0f}ms)"

    duration_min = duration_s / 60
    if duration_min < MIN_TO_H_THRESHOLD:
        # 小于1.5小时，显示分+秒
        return f"{duration_min:.1f}min ({duration_s:.0f}s)"

    # 大于等于1.5小时，显示时+分
    duration_h = duration_min / 60
    return f"{duration_h:.1f}h ({duration_min:.0f}min)"


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
    """读取 JSON 文件。

    Args:
        path: JSON 文件路径。

    Returns:
        dict: 读取失败或文件不存在时返回空字典。
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
        logger.opt(exception=True).error(f"文件不存在，位置: {path}")
        return {}
    except json.JSONDecodeError as e:
        logger.opt(exception=True).error(f"JSON 解析错误，位置: {path}, 错误: {e}")
        return {}
    except Exception as e:
        logger.opt(exception=True).error(f"未知错误，位置: {path}, 错误: {e}")
        return {}


def dump_msgpack(obj, path: str | PathLike | Path):
    """
    将对象使用 MessagePack 序列化并写入文件

    :param obj: 要序列化的对象
    :param path: 文件路径
    """
    path = Path(path)
    with path.open("wb") as f:
        msgpack.dump(obj, f)


def load_msgpack(path: str | PathLike | Path) -> dict:
    """从文件读取并使用 MessagePack 反序列化对象。

    Args:
        path: MessagePack 文件路径。

    Returns:
        dict: 反序列化后的对象；读取失败或文件不存在时返回空字典。
    """
    path = Path(path)
    if not path.exists():
        return {}

    try:
        with path.open("rb") as f:
            return msgpack.load(f, raw=False)
    except msgpack.exceptions.UnpackException as e:
        logger.opt(exception=True).error(f"MessagePack 解析错误，位置: {path}, 错误: {e}")
        return {}
    except Exception as e:
        logger.opt(exception=True).error(f"加载 MessagePack 文件时发生未知错误，位置: {path}, 错误: {e}")
        return {}


def dump_yaml(data: dict, path: PathLike | str | Path) -> None:
    """
    将字典写入YAML文件，保留格式和顺序。

    :param data: 要写入的字典数据。
    :param path: 输出文件路径。
    """
    path = Path(path)
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f)


def load_yaml(path: PathLike | str | Path) -> dict:
    """从 YAML 文件加载数据。

    Args:
        path: 输入文件路径。

    Returns:
        dict: 从 YAML 文件加载的字典数据；读取失败或文件不存在时返回空字典。
    """
    path = Path(path)
    if not path.exists():
        return {}

    yaml = YAML(typ="safe")
    try:
        with path.open("r", encoding="utf-8") as f:
            return yaml.load(f) or {}
    except Exception as e:
        logger.opt(exception=True).error(f"加载 YAML 文件时出错: {path}, 错误: {e}")
        return {}


def list2dict(data, key):
    """
    将类似[{'id':1, 'xx':xx}, ...]的列表转换为字典
    :param data:
    :param key:
    :return:
    """
    return {item[key]: item for item in data}


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
