"""manager 子域共享的数据文件读写辅助。"""

from __future__ import annotations

import time
from pathlib import Path

from loguru import logger

from lol_audio_unpack.utils.common import (
    dump_json,
    dump_msgpack,
    dump_yaml,
    format_duration,
    load_json,
    load_msgpack,
    load_yaml,
)


def find_data_file(path: Path, *, dev_mode: bool) -> Path | None:
    """查找数据文件的实际路径。

    Args:
        path: 文件路径，可带或不带后缀。
        dev_mode: 是否启用开发模式。

    Returns:
        实际存在的文件路径；若所有候选文件都不存在则返回 ``None``。
    """
    files_to_check = []

    if path.suffix:
        files_to_check.append(path)
    else:
        formats_priority = [".yml", ".json", ".msgpack"] if dev_mode else [".msgpack", ".yml", ".json"]
        files_to_check = [path.with_suffix(suffix) for suffix in formats_priority]

    for file_to_try in files_to_check:
        if file_to_try.exists():
            return file_to_try

    return None


def read_data(path: Path, *, dev_mode: bool = False) -> dict:
    """按环境优先级读取数据文件。

    Args:
        path: 文件路径，可带或不带后缀。
        dev_mode: 是否启用开发模式。

    Returns:
        读取到的数据字典；读取失败时返回空字典。
    """
    start_time = time.time()
    actual_file = find_data_file(path, dev_mode=dev_mode)

    file_search_time = time.time()
    search_duration_ms = (file_search_time - start_time) * 1000
    logger.trace(f"文件查找耗时: {format_duration(search_duration_ms)}")

    if not actual_file:
        if not path.suffix:
            logger.warning(f"在 {path.parent} 未找到任何格式的数据文件 (base: {path.name})")
        else:
            logger.warning(f"指定的数据文件不存在: {path}，将返回空字典")

        total_time_ms = (time.time() - start_time) * 1000
        logger.debug(f"read_data 总耗时: {format_duration(total_time_ms)}")
        return {}

    suffix = actual_file.suffix
    loader = None
    if suffix == ".json":
        loader = load_json
    elif suffix == ".msgpack":
        loader = load_msgpack
    elif suffix in [".yaml", ".yml"]:
        loader = load_yaml

    if not loader:
        logger.error(f"不支持的文件格式: {suffix} (来自: {actual_file})")
        total_time_ms = (time.time() - start_time) * 1000
        logger.debug(f"read_data 总耗时: {format_duration(total_time_ms)}")
        return {}

    file_size_mb = actual_file.stat().st_size / (1024 * 1024)
    logger.trace(f"找到数据文件: {actual_file} (大小: {file_size_mb:.2f}MB, 格式: {suffix})")

    try:
        read_start_time = time.time()
        result = loader(actual_file)
        read_end_time = time.time()

        read_duration_ms = (read_end_time - read_start_time) * 1000
        logger.trace(
            f"文件读取完成: {actual_file.name} | 耗时: {format_duration(read_duration_ms)} | "
            f"读取速度: {file_size_mb / (read_duration_ms / 1000):.2f}MB/s"
        )

        total_time_ms = (time.time() - start_time) * 1000
        logger.debug(f"read_data 总耗时: {format_duration(total_time_ms)}")
        return result

    except Exception as exc:
        logger.opt(exception=True).error(f"读取文件时出错: {actual_file}, 错误: {exc}")
        total_time_ms = (time.time() - start_time) * 1000
        logger.debug(f"read_data 总耗时: {format_duration(total_time_ms)}")
        return {}


def write_data(data: dict, base_path: Path, *, dev_mode: bool) -> None:
    """根据环境选择格式并写入数据文件。

    Args:
        data: 要写入的数据。
        base_path: 不带后缀的基础文件路径。
        dev_mode: 是否启用开发模式。
    """
    fmt = "yml" if dev_mode else "msgpack"
    path = base_path.with_suffix(f".{fmt}")
    try:
        if fmt == "yml":
            dump_yaml(data, path)
        elif fmt == "json":
            dump_json(data, path)
        else:
            dump_msgpack(data, path)
        logger.trace(f"成功写入数据到: {path}")
    except Exception as exc:
        logger.opt(exception=True).error(f"写入文件失败: {path}, 错误: {exc}")


def needs_update(base_path: Path, current_version: str, force_update: bool, *, dev_mode: bool) -> bool:
    """检查目标文件是否需要更新。

    Args:
        base_path: 要检查的文件基础路径，不带后缀。
        current_version: 当前游戏版本。
        force_update: 是否强制更新。
        dev_mode: 是否启用开发模式。

    Returns:
        若需要更新则返回 ``True``。
    """
    if force_update:
        return True

    actual_file = find_data_file(base_path, dev_mode=dev_mode)
    if not actual_file:
        return True

    data = read_data(base_path, dev_mode=dev_mode)
    if not data:
        return True

    data_version = data.get("metadata", {}).get("gameVersion")
    if not data_version:
        return True

    if data_version == current_version:
        logger.debug(f"文件已是最新版本 ({current_version})，跳过更新: {base_path.name}")
        return False

    return True


__all__ = [
    "find_data_file",
    "needs_update",
    "read_data",
    "write_data",
]
