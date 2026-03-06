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
from typing import TYPE_CHECKING

from loguru import logger

from lol_audio_unpack.app_context import SourceMode
from lol_audio_unpack.utils.common import (
    dump_json,
    dump_msgpack,
    dump_yaml,
    format_duration,
    load_json,
    load_msgpack,
    load_yaml,
)
from lol_audio_unpack.utils.versioning import extract_windows_file_version, normalize_patch_version

if TYPE_CHECKING:
    from lol_audio_unpack.app_context import AppContext


def find_data_file(path: Path, *, dev_mode: bool) -> Path | None:
    """
    查找数据文件的实际路径。
    如果路径包含后缀，则直接检查该文件。
    如果路径不含后缀，则按优先级顺序查找第一个存在的文件。

    开发模式下，优先使用人类可读的格式。

    :param path: 文件路径（可带或不带后缀）
    :param dev_mode: 是否启用开发模式。
    :return: 实际存在的文件路径，如果都不存在则返回None
    """
    files_to_check = []

    # 1. 确定要检查的文件列表
    if path.suffix:
        # 如果指定了后缀，只检查这一个文件
        files_to_check.append(path)
    else:
        # 如果未指定后缀，按优先级生成待检查文件列表
        formats_priority = [".yml", ".json", ".msgpack"] if dev_mode else [".msgpack", ".yml", ".json"]
        files_to_check = [path.with_suffix(s) for s in formats_priority]

    # 2. 返回第一个存在的文件
    for file_to_try in files_to_check:
        if file_to_try.exists():
            return file_to_try

    return None


def read_data(path: Path, *, dev_mode: bool = False) -> dict:
    """
    智能读取数据文件。
    如果路径包含后缀，则直接读取该文件。
    如果路径不含后缀，则按优先级顺序查找并读取第一个存在的文件。

    开发模式下，优先使用人类可读的格式。

    :param path: 文件路径（可带或不带后缀）
    :param dev_mode: 是否启用开发模式。
    :return: 读取的数据字典
    """
    start_time = time.time()

    # 1. 查找实际存在的文件
    actual_file = find_data_file(path, dev_mode=dev_mode)

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


def write_data(data: dict, base_path: Path, *, dev_mode: bool) -> None:
    """
    根据环境自动选择最佳格式写入数据文件。
    开发模式下写入YAML，生产模式下写入MessagePack。

    :param data: 要写入的数据
    :param base_path: 不带后缀的基础文件路径
    :param dev_mode: 是否启用开发模式。
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

    return normalize_patch_version(data["version"])


def get_lcu_version(game_path: Path) -> str | None:
    """读取本地 ``LeagueClient.exe`` 的补丁版本。

    Args:
        game_path: 游戏根目录。

    Returns:
        若存在且成功解析，返回 ``major.minor`` 形式的版本号；否则返回 ``None``。
    """
    exe_path = game_path / "LeagueClient" / "LeagueClient.exe"
    if not exe_path.is_file():
        return None

    try:
        payload = exe_path.read_bytes()
        return normalize_patch_version(extract_windows_file_version(payload))
    except (OSError, ValueError) as exc:
        logger.warning(f"无法从 LeagueClient.exe 解析版本，已跳过 LCU 一致性校验: {exe_path} | {exc}")
        return None


def validate_local_path_version(game_path: Path, game_version: str) -> None:
    """校验本地 GAME 与 LCU 的主版本是否一致。

    Args:
        game_path: 游戏根目录。
        game_version: 从 `content-metadata.json` 提取的补丁版本。
    """
    lcu_version = get_lcu_version(game_path)
    if lcu_version is None:
        logger.debug("未执行本地 LCU 一致性校验：缺少或无法读取 LeagueClient.exe 版本。")
        return

    if lcu_version == game_version:
        logger.debug(f"本地 GAME / LCU 主版本一致: {game_version}")
        return

    logger.warning(
        "检测到本地 GAME / LCU 主版本不一致："
        f"GAME={game_version}, LCU={lcu_version}。请确认传入的游戏目录是否完整且自洽。"
    )


def resolve_context_version(ctx: "AppContext") -> str:
    """根据来源模式解析当前运行版本。

    Args:
        ctx: 运行时上下文。

    Returns:
        当前运行使用的补丁版本号。

    Raises:
        ValueError: 当远端快照缺少版本信息时抛出。
    """
    cached_version = ctx.runtime_cache.get("resolved_runtime_version")
    if isinstance(cached_version, str) and cached_version:
        return cached_version

    if ctx.config.source_mode is SourceMode.REMOTE_SNAPSHOT:
        remote_snapshot = ctx.config.remote_snapshot
        if remote_snapshot is None:
            raise ValueError("REMOTE_SNAPSHOT 模式缺少远端快照配置，无法解析版本。")
        version = remote_snapshot.version
    else:
        version = get_game_version(Path(ctx.config.game_path))
        if not ctx.runtime_cache.get("local_version_validated", False):
            validate_local_path_version(Path(ctx.config.game_path), version)
            ctx.runtime_cache["local_version_validated"] = True

    ctx.runtime_cache["resolved_runtime_version"] = version
    return version


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


def needs_update(base_path: Path, current_version: str, force_update: bool, *, dev_mode: bool) -> bool:
    """
    检查文件是否需要更新的通用函数

    :param base_path: 要检查的文件的基础路径（不带后缀）
    :param current_version: 当前游戏版本
    :param force_update: 是否强制更新
    :param dev_mode: 是否启用开发模式。
    :return: 如果需要更新，则返回True
    """
    if force_update:
        return True

    # 1. 首先检查文件是否存在，避免不必要的警告日志
    actual_file = find_data_file(base_path, dev_mode=dev_mode)
    if not actual_file:
        return True  # 文件不存在，需要更新

    # 2. 文件存在，读取内容检查版本
    data = read_data(base_path, dev_mode=dev_mode)
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
