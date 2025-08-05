# 🐍 Although that way may not be obvious at first unless you're Dutch.
# 🐼 尽管这方法一开始并非如此直观，除非你是荷兰人
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2025/7/30 7:38
# @Update  : 2025/8/6 5:56
# @Detail  : Manager模块的通用函数


import json
import os
import re
import sys
import time
from datetime import datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as get_package_version
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
from lol_audio_unpack.utils.config import config


def find_data_file(path: Path) -> Path | None:
    """
    查找数据文件的实际路径。
    如果路径包含后缀，则直接检查该文件。
    如果路径不含后缀，则按优先级顺序查找第一个存在的文件。

    开发模式下，优先使用人类可读的格式。

    :param path: 文件路径（可带或不带后缀）
    :return: 实际存在的文件路径，如果都不存在则返回None
    """
    files_to_check = []

    # 1. 确定要检查的文件列表
    if path.suffix:
        # 如果指定了后缀，只检查这一个文件
        files_to_check.append(path)
    else:
        # 如果未指定后缀，按优先级生成待检查文件列表
        formats_priority = [".yml", ".json", ".msgpack"] if config.is_dev_mode() else [".msgpack", ".yml", ".json"]
        files_to_check = [path.with_suffix(s) for s in formats_priority]

    # 2. 返回第一个存在的文件
    for file_to_try in files_to_check:
        if file_to_try.exists():
            return file_to_try

    return None


def read_data(path: Path) -> dict:
    """
    智能读取数据文件。
    如果路径包含后缀，则直接读取该文件。
    如果路径不含后缀，则按优先级顺序查找并读取第一个存在的文件。

    开发模式下，优先使用人类可读的格式。

    :param path: 文件路径（可带或不带后缀）
    :return: 读取的数据字典
    """
    start_time = time.time()

    # 1. 查找实际存在的文件
    actual_file = find_data_file(path)

    file_search_time = time.time()
    search_duration_ms = (file_search_time - start_time) * 1000
    logger.trace(f"文件查找耗时: {format_duration(search_duration_ms)}")

    # 2. 如果未找到文件，记录警告并返回空字典
    if not actual_file:
        if not path.suffix:
            logger.warning(f"在 {path.parent} 未找到任何格式的数据文件 (base: {path.name})")
        else:
            logger.warning(f"指定的数据文件不存在: {path}，将返回空字典")

        total_time_ms = (time.time() - start_time) * 1000
        logger.debug(f"read_data 总耗时: {format_duration(total_time_ms)}")
        return {}

    # 3. 读取找到的文件
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

    # 4. 执行文件读取
    file_size_mb = actual_file.stat().st_size / (1024 * 1024)
    logger.trace(f"找到数据文件: {actual_file} (大小: {file_size_mb:.2f}MB, 格式: {suffix})")

    try:
        read_start_time = time.time()
        result = loader(actual_file)
        read_end_time = time.time()

        read_duration_ms = (read_end_time - read_start_time) * 1000
        logger.trace(
            f"文件读取完成: {actual_file.name} | 耗时: {format_duration(read_duration_ms)} | 读取速度: {file_size_mb / (read_duration_ms / 1000):.2f}MB/s"
        )

        total_time_ms = (time.time() - start_time) * 1000
        logger.debug(f"read_data 总耗时: {format_duration(total_time_ms)}")
        return result

    except Exception as e:
        logger.error(f"读取文件时出错: {actual_file}, 错误: {e}")
        total_time_ms = (time.time() - start_time) * 1000
        logger.debug(f"read_data 总耗时: {format_duration(total_time_ms)}")
        return {}


def write_data(data: dict, base_path: Path) -> None:
    """
    根据环境自动选择最佳格式写入数据文件。
    开发模式下写入YAML，生产模式下写入MessagePack。

    :param data: 要写入的数据
    :param base_path: 不带后缀的基础文件路径
    """
    fmt = "yml" if config.is_dev_mode() else "msgpack"
    path = base_path.with_suffix(f".{fmt}")
    try:
        if fmt == "yml":
            dump_yaml(data, path)
        elif fmt == "json":
            dump_json(data, path)
        else:
            dump_msgpack(data, path)
        logger.trace(f"成功写入数据到: {path}")
    except Exception as e:
        logger.error(f"写入文件失败: {path}, 错误: {e}")


def get_game_version(game_path: Path) -> str:
    """
    获取游戏版本

    :param game_path: 游戏根目录路径
    :return: 游戏版本号
    """
    meta = game_path / "Game" / "content-metadata.json"
    if not meta.exists():
        raise FileNotFoundError("content-metadata.json 文件不存在，无法判断版本信息")

    with open(meta, encoding="utf-8") as f:
        data = json.load(f)

    version_v = data["version"]

    if m := re.match(r"^(\d+\.\d+)\.", version_v):
        return m.group(1)
    raise ValueError(f"无法解析版本号: {version_v}")


def create_metadata_object(game_version: str, languages: list[str]) -> dict:
    """
    创建一个包含标准化元数据的新对象。

    :param game_version: 游戏客户端版本。
    :param languages: 包含的语言列表。
    :return: 一个包含所有元数据的字典。
    """
    try:
        script_version = get_package_version("lol-audio-unpack")
    except PackageNotFoundError:
        script_version = "0.0.0-dev"
        logger.warning("无法获取包版本，请使用 'pip install -e .' 在可编辑模式下安装。将版本设置为 '0.0.0-dev'。")

    metadata = {
        "gameVersion": game_version,
        "scriptName": "lol-audio-unpack",
        "scriptWebsite": "https://github.com/Virace/lol-audio-unpack",
        "scriptVersion": script_version,
        "schemaVersion": "1.0",
        "createdAt": datetime.now().isoformat(),
        "languages": languages,
        "platform": {
            "os": os.name,
            "pythonVersion": sys.version.split(" ")[0],
        },
    }
    return {"metadata": metadata}


def needs_update(base_path: Path, current_version: str, force_update: bool) -> bool:
    """
    检查文件是否需要更新的通用函数

    :param base_path: 要检查的文件的基础路径（不带后缀）
    :param current_version: 当前游戏版本
    :param force_update: 是否强制更新
    :return: 如果需要更新，则返回True
    """
    if force_update:
        return True

    # 1. 首先检查文件是否存在，避免不必要的警告日志
    actual_file = find_data_file(base_path)
    if not actual_file:
        return True  # 文件不存在，需要更新

    # 2. 文件存在，读取内容检查版本
    data = read_data(base_path)
    if not data:
        return True  # 读取失败，需要更新

    # 3. 从 metadata 对象中获取版本信息
    data_version = data.get("metadata", {}).get("gameVersion")

    if not data_version:
        return True  # 没有版本信息，需要更新

    if data_version == current_version:
        logger.debug(f"文件已是最新版本 ({current_version})，跳过更新: {base_path.name}")
        return False

    return True
