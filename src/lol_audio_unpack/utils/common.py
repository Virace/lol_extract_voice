"""提供仍在项目中使用的通用序列化、格式化与单例工具。"""

from __future__ import annotations

import json
import re
import threading
from json import JSONEncoder
from os import PathLike
from pathlib import Path
from typing import Any

import msgpack
from loguru import logger
from ruamel.yaml import YAML

__all__ = [
    "Singleton",
    "dump_json",
    "dump_msgpack",
    "dump_yaml",
    "format_duration",
    "format_region",
    "load_json",
    "load_msgpack",
    "load_yaml",
    "sanitize_filename",
]


def sanitize_filename(filename: str, replacement: str = "_") -> str:
    """清理文件名中的非法字符。

    Args:
        filename: 原始文件名或路径片段。
        replacement: 用于替换非法字符的字符串。

    Returns:
        适合写入文件系统的安全文件名。
    """

    # Windows 文件名非法字符: < > : " / \ | ? *
    # 同时包括控制字符 (ASCII 0-31)。
    illegal_chars_re = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
    cleaned = illegal_chars_re.sub(replacement, filename)
    # Windows 不允许文件名以空格或点结尾。
    cleaned = cleaned.rstrip(" .")
    # 如果清理后为空，使用兜底名称，避免生成空文件名。
    return cleaned if cleaned else "unnamed"


def format_duration(duration_ms: float) -> str:
    """按当前阈值规则格式化耗时。

    Args:
        duration_ms: 耗时，单位毫秒。

    Returns:
        人类可读的耗时字符串。
    """

    # 保持历史阈值：按 1.5 倍关系切换单位，避免输出频繁抖动。
    ms_to_s_threshold = 1500
    s_to_min_threshold = 90
    min_to_h_threshold = 90

    if duration_ms < ms_to_s_threshold:
        # 小于 1.5 秒时，只显示毫秒。
        return f"{duration_ms:.0f}ms"

    duration_s = duration_ms / 1000
    if duration_s < s_to_min_threshold:
        # 小于 1.5 分钟时，显示秒和原始毫秒。
        return f"{duration_s:.1f}s ({duration_ms:.0f}ms)"

    duration_min = duration_s / 60
    if duration_min < min_to_h_threshold:
        # 小于 1.5 小时时，显示分钟和总秒数。
        return f"{duration_min:.1f}min ({duration_s:.0f}s)"

    # 更长耗时统一收口为小时 + 分钟，避免日志过宽。
    duration_h = duration_min / 60
    return f"{duration_h:.1f}h ({duration_min:.0f}min)"


class Singleton(type):
    """提供线程安全实例缓存的单例元类。"""

    _instances: dict[type, Any] = {}
    _lock = threading.Lock()

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        """按类型缓存实例。

        Args:
            *args: 传给构造函数的位置参数。
            **kwargs: 传给构造函数的关键字参数。

        Returns:
            当前类型对应的单例实例。
        """

        if cls not in cls._instances:
            with cls._lock:
                # 双重检查保证并发场景下只创建一次实例。
                if cls not in cls._instances:
                    cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


def format_region(region: str) -> str:
    """规范化语言区域名称。

    Args:
        region: 原始区域字符串，例如 ``zh_CN`` 或 ``default``。

    Returns:
        规范化后的区域字符串。
    """

    if region.lower() == "default":
        return region
    return region[:3].lower() + region[3:].upper()


def dump_json(
    obj: Any,
    path: str | PathLike | Path,
    ensure_ascii: bool = False,
    cls: type[JSONEncoder] | None = None,
    indent: int | None = None,
) -> None:
    """将对象写入 JSON 文件。

    Args:
        obj: 待写入的对象。
        path: 输出文件路径。
        ensure_ascii: 是否转义非 ASCII 字符。
        cls: 可选自定义 JSON 编码器。
        indent: 缩进级别，``None`` 或 ``0`` 表示紧凑输出。
    """

    target = Path(path)
    with target.open("w+", encoding="utf-8") as file:
        json.dump(obj, file, ensure_ascii=ensure_ascii, cls=cls, indent=indent)


def load_json(path: str | PathLike | Path) -> dict:
    """读取 JSON 文件。

    Args:
        path: JSON 文件路径。

    Returns:
        反序列化后的字典；读取失败时返回空字典。
    """

    target = Path(path)
    # 历史行为要求：缺文件时直接返回空字典，不把不存在视为异常。
    if not target.exists():
        return {}

    try:
        with target.open(encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        logger.opt(exception=True).error(f"文件不存在，位置: {target}")
        return {}
    except json.JSONDecodeError as exc:
        logger.opt(exception=True).error(f"JSON 解析错误，位置: {target}, 错误: {exc}")
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.opt(exception=True).error(f"未知错误，位置: {target}, 错误: {exc}")
        return {}


def dump_msgpack(obj: Any, path: str | PathLike | Path) -> None:
    """将对象写入 MessagePack 文件。

    Args:
        obj: 待序列化对象。
        path: 输出文件路径。
    """

    target = Path(path)
    with target.open("wb") as file:
        msgpack.dump(obj, file)


def load_msgpack(path: str | PathLike | Path) -> dict:
    """读取 MessagePack 文件。

    Args:
        path: MessagePack 文件路径。

    Returns:
        反序列化后的字典；读取失败时返回空字典。
    """

    target = Path(path)
    # 与 JSON/YAML 保持一致：调用方可把缺文件视为“暂无数据”。
    if not target.exists():
        return {}

    try:
        with target.open("rb") as file:
            return msgpack.load(file, raw=False)
    except msgpack.exceptions.UnpackException as exc:
        logger.opt(exception=True).error(f"MessagePack 解析错误，位置: {target}, 错误: {exc}")
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.opt(exception=True).error(f"加载 MessagePack 文件时发生未知错误，位置: {target}, 错误: {exc}")
        return {}


def dump_yaml(data: dict, path: PathLike | str | Path) -> None:
    """将字典写入 YAML 文件。

    Args:
        data: 待写入字典。
        path: 输出文件路径。
    """

    target = Path(path)
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    with target.open("w", encoding="utf-8") as file:
        yaml.dump(data, file)


def load_yaml(path: PathLike | str | Path) -> dict:
    """从 YAML 文件读取字典数据。

    Args:
        path: 输入文件路径。

    Returns:
        读取到的字典；读取失败时返回空字典。
    """

    target = Path(path)
    # 缺文件时直接回空字典，便于上层统一做“无配置”分支。
    if not target.exists():
        return {}

    yaml = YAML(typ="safe")
    try:
        with target.open("r", encoding="utf-8") as file:
            return yaml.load(file) or {}
    except Exception as exc:  # noqa: BLE001
        logger.opt(exception=True).error(f"加载 YAML 文件时出错: {target}, 错误: {exc}")
        return {}
