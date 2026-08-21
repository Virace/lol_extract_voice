"""manager 子域共享的数据文件读写辅助。"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from loguru import logger

from lol_audio_unpack.manager.errors import ArtifactWriteError
from lol_audio_unpack.utils.common import dump_msgpack, dump_yaml, format_duration, load_json, load_msgpack, load_yaml


def _replace_file(target: Path, writer: Callable[[Path], object], *, write_stage: str) -> Path:
    """在目标同目录准备完整文件后执行原子替换。

    Args:
        target: 带后缀的正式目标路径。
        writer: 只向所给临时路径写入完整内容的函数。
        write_stage: writer 失败时写入语义异常的阶段名。

    Returns:
        成功替换的目标路径。

    Raises:
        ArtifactWriteError: 准备、写入、同步或替换失败。
    """
    temp_path: Path | None = None
    stage = "prepare"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
        )
        temp_path = Path(temp_name)
        os.close(descriptor)

        stage = write_stage
        writer(temp_path)

        # Windows 的 fsync 需要可写句柄；内容不再修改，只借此确保 replace 前完成文件同步。
        stage = "fsync"
        with temp_path.open("r+b") as file:
            os.fsync(file.fileno())

        stage = "replace"
        os.replace(temp_path, target)
        return target
    except Exception as exc:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                logger.opt(exception=True).warning(f"清理 artifact 临时文件失败: {temp_path}")
        raise ArtifactWriteError(target, stage) from exc


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


def read_data(path: Path, *, dev_mode: bool = False, log_errors: bool = True) -> dict:
    """按环境优先级读取数据文件。

    Args:
        path: 文件路径，可带或不带后缀。
        dev_mode: 是否启用开发模式。
        log_errors: 反序列化失败时是否在当前边界记录 traceback。

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
        if log_errors:
            logger.opt(exception=True).error(f"读取文件时出错: {actual_file}, 错误: {exc}")
        total_time_ms = (time.time() - start_time) * 1000
        logger.debug(f"read_data 总耗时: {format_duration(total_time_ms)}")
        return {}


def write_data(data: dict, base_path: Path, *, dev_mode: bool) -> Path:
    """根据环境选择格式并原子替换数据文件。

    Args:
        data: 要写入的数据。
        base_path: 不带后缀的基础文件路径。
        dev_mode: 是否启用开发模式。

    Returns:
        成功替换的实际目标路径。

    Raises:
        ArtifactWriteError: 无法完成序列化、同步或原子替换。
    """
    fmt = "yml" if dev_mode else "msgpack"
    path = base_path.with_suffix(f".{fmt}")
    serializer = dump_yaml if dev_mode else dump_msgpack
    target = _replace_file(path, lambda temp: serializer(data, temp), write_stage="serialize")
    logger.trace(f"成功写入数据到: {target}")
    return target


def write_bytes_atomic(data: bytes, path: Path) -> Path:
    """以原子替换方式写入精确字节。

    Args:
        data: 要持久化的完整字节。
        path: 带后缀的正式目标路径。

    Returns:
        成功替换的目标路径。

    Raises:
        ArtifactWriteError: 无法完成写入、同步或原子替换。
    """
    return _replace_file(path, lambda temp: temp.write_bytes(data), write_stage="write")


def copy_file_atomic(source: Path, target: Path) -> Path:
    """复制完整文件并以原子替换方式发布。

    Args:
        source: 要复制的源文件。
        target: 带后缀的正式目标路径。

    Returns:
        成功替换的目标路径。

    Raises:
        ArtifactWriteError: 无法完成复制、同步或原子替换。
    """
    return _replace_file(target, lambda temp: shutil.copy2(source, temp), write_stage="copy")


def needs_update(
    base_path: Path,
    current_version: str,
    force_update: bool,
    *,
    dev_mode: bool,
    resource_schema: int | None = None,
) -> bool:
    """检查目标文件是否需要更新。

    Args:
        base_path: 要检查的文件基础路径，不带后缀。
        current_version: 当前游戏版本。
        force_update: 是否强制更新。
        dev_mode: 是否启用开发模式。
        resource_schema: 本地派生产物要求的 resource schema；为空时不检查。

    Returns:
        若需要更新则返回 ``True``。
    """
    if force_update:
        return True

    actual_file = find_data_file(base_path, dev_mode=dev_mode)
    if not actual_file:
        return True

    data = read_data(base_path, dev_mode=dev_mode)
    data_version = data.get("metadata", {}).get("gameVersion") if data else None
    if not data_version:
        return True

    if resource_schema is not None and data.get("resourceSchemaVersion") != resource_schema:
        logger.debug(f"资源 schema 已过期，需要重新生成: {base_path.name}")
        return True

    if data_version != current_version:
        return True

    logger.debug(f"文件已是最新版本 ({current_version})，跳过更新: {base_path.name}")
    return False


__all__ = [
    "copy_file_atomic",
    "find_data_file",
    "needs_update",
    "read_data",
    "write_bytes_atomic",
    "write_data",
]
