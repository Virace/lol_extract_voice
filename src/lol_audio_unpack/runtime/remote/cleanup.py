"""远端准备流程的清理与底层文件辅助函数。"""

from __future__ import annotations

import asyncio
import os
import shutil
import threading
from pathlib import Path, PurePosixPath
from typing import Any

from loguru import logger


def run_sync(coroutine: Any) -> Any:
    """在同步上下文中执行协程。

    Args:
        coroutine: 待执行的协程对象。

    Returns:
        协程执行结果。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coroutine)
        except BaseException as exc:  # noqa: BLE001
            error["value"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if "value" in error:
        raise error["value"]
    return result.get("value")


def get_lcu_path(file_name: str, *, plugin_suffix: str) -> PurePosixPath | None:
    """提取相对于 LCU 插件根目录的路径。

    Args:
        file_name: manifest 中记录的文件路径。
        plugin_suffix: LCU 插件根目录后缀。

    Returns:
        插件根目录下的相对路径；若不在目标目录下，返回 `None`。
    """
    normalized_parts = [part for part in PurePosixPath(file_name).parts if part not in {".", ""}]
    lowered_parts = [part.lower() for part in normalized_parts]
    suffix_parts = plugin_suffix.split("/")
    for index in range(len(lowered_parts) - len(suffix_parts) + 1):
        if lowered_parts[index : index + len(suffix_parts)] != suffix_parts:
            continue
        relative_parts = normalized_parts[index + len(suffix_parts) :]
        if not relative_parts:
            return PurePosixPath()
        return PurePosixPath(*relative_parts)
    return None


def link_or_copy(source_path: Path, target_path: Path) -> None:
    """优先硬链接，失败时回退复制。

    Args:
        source_path: 源文件路径。
        target_path: 目标文件路径。
    """
    if target_path.exists():
        return

    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source_path, target_path)
    except OSError:
        shutil.copy2(source_path, target_path)


def load_registry(runtime_cache: dict[str, Any], *, cache_key: str) -> dict[str, set[str]]:
    """获取或初始化远端清理登记表。

    Args:
        runtime_cache: 运行时缓存字典。
        cache_key: 远端清理登记表在缓存中的键名。

    Returns:
        规范化后的清理登记表。
    """
    registry = runtime_cache.get(cache_key)
    if isinstance(registry, dict):
        return registry

    registry = {
        "cached_lcu_wads": set(),
        "prepared_lcu_wads": set(),
        "bin_input_files": set(),
        "bin_input_flags": set(),
        "cached_game_wads": set(),
        "prepared_game_wads": set(),
    }
    runtime_cache[cache_key] = registry
    return registry


def track_paths(
    registry: dict[str, set[str]],
    key: str,
    paths: list[Path] | tuple[Path, ...],
) -> None:
    """登记可清理文件路径。

    Args:
        registry: 清理登记表。
        key: 当前路径组的键名。
        paths: 需要登记的路径集合。
    """
    registry[key].update(str(path) for path in paths)


def remove_paths(paths: set[str], *, dry_run: bool) -> int:
    """删除或统计已登记路径数量。

    Args:
        paths: 已登记的原始路径字符串集合。
        dry_run: 为 `True` 时只统计不删除。

    Returns:
        实际删除或将要删除的路径数量。
    """
    removed_count = 0
    for raw_path in list(paths):
        path = Path(raw_path)
        if dry_run:
            if path.exists():
                removed_count += 1
            continue
        try:
            if path.exists():
                path.unlink()
                removed_count += 1
        except OSError:
            logger.warning(f"清理远端产物失败: {path}")
        finally:
            paths.discard(raw_path)
    return removed_count


def prune_empty_tree(root: Path) -> None:
    """删除给定根目录下的空目录。

    Args:
        root: 需要向下清理的目录根。
    """
    if not root.exists():
        return

    for current_root, _, _ in os.walk(root, topdown=False):
        current_path = Path(current_root)
        try:
            if any(current_path.iterdir()):
                continue
        except OSError:
            continue
        try:
            current_path.rmdir()
        except OSError:
            continue
