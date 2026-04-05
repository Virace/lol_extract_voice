"""批量解包任务编排。"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING

from league_tools.formats import WAD
from loguru import logger

from lol_audio_unpack.manager import DataReader
from lol_audio_unpack.model import generate_champion_tasks, generate_map_tasks

from .entity import unpack_champion, unpack_map

if TYPE_CHECKING:
    from lol_audio_unpack.app.types import AppContext


def execute_tasks(  # noqa: PLR0913
    tasks: list[tuple[str, int, str]],
    reader: DataReader,
    max_workers: int = 4,
    *,
    ctx: AppContext,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
    persisted_wem_callback: Callable[[Path], None] | None = None,
) -> None:
    """执行批量解包任务。

    Args:
        tasks: 任务元组列表 ``[(entity_type, id, description), ...]``。
        reader: 数据读取器实例。
        max_workers: 最大并发线程数。
        ctx: 运行时上下文。
        progress_callback: 每个实体处理结束后的可选进度回调。
        persisted_wem_callback: WEM 落盘后的附加回调。
    """
    if not tasks:
        logger.warning("没有任何任务需要执行")
        return

    start_time = time.time()
    total_tasks = len(tasks)
    champion_count = sum(1 for entity_type, _, _ in tasks if entity_type == "champion")
    map_count = sum(1 for entity_type, _, _ in tasks if entity_type == "map")
    summary_parts = []
    if champion_count > 0:
        summary_parts.append(f"{champion_count} 个英雄")
    if map_count > 0:
        summary_parts.append(f"{map_count} 个地图")
    totals_by_type = {
        "champion": champion_count,
        "map": map_count,
    }
    finished_by_type = {
        "champion": 0,
        "map": 0,
    }
    progress_lock = threading.Lock() if max_workers > 1 else None

    logger.info(
        f"开始解包 {total_tasks} 个实体 ({' 和 '.join(summary_parts)})，"
        f"模式: {'多线程' if max_workers > 1 else '单线程'} (workers: {max_workers})"
    )

    failed_count = 0
    show_exception = bool(getattr(ctx.config, "dev_mode", False))

    # 解包阶段的 WAD 缓存以整轮 batch 为单位共享，
    # 这样同一个实体/多个实体命中同一 WAD 时都不会重复打开文件句柄。
    wad_cache: dict[Path, WAD] = {}
    cache_lock = threading.Lock() if max_workers > 1 else None

    def unpack_one(entity_type: str, entity_id: int) -> None:
        common_kwargs: dict[str, object] = {
            "wad_cache": wad_cache,
            "cache_lock": cache_lock,
            "ctx": ctx,
            "persisted_wem_callback": persisted_wem_callback,
        }
        if entity_type == "champion":
            unpack_champion(entity_id, reader, **common_kwargs)
        elif entity_type == "map":
            unpack_map(entity_id, reader, **common_kwargs)
        else:
            raise ValueError(f"未知的实体类型: {entity_type}")

    def emit_running_progress(entity_type: str, description: str) -> None:
        if progress_callback is None:
            return

        def _emit() -> None:
            progress_callback(
                entity_type,
                finished_by_type.get(entity_type, 0),
                max(totals_by_type.get(entity_type, total_tasks), 1),
                f"正在处理: {description}",
            )

        if progress_lock is None:
            _emit()
            return

        with progress_lock:
            _emit()

    def unpack_one_with_progress(entity_type: str, entity_id: int, description: str) -> None:
        emit_running_progress(entity_type, description)
        unpack_one(entity_type, entity_id)

    if max_workers > 1:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_task = {
                executor.submit(unpack_one_with_progress, entity_type, entity_id, description): (entity_type, description)
                for entity_type, entity_id, description in tasks
            }
            finished_count = 0
            for future in as_completed(future_to_task):
                entity_type, description = future_to_task[future]
                finished_count += 1
                finished_by_type[entity_type] = finished_by_type.get(entity_type, 0) + 1

                try:
                    future.result()
                    progress_message = f"{description} 解包完成"
                    logger.info(f"进度: {finished_count}/{total_tasks} - {progress_message}。")
                except Exception as exc:  # noqa: BLE001
                    failed_count += 1
                    progress_message = f"{description} 解包失败"
                    logger.opt(exception=show_exception).warning(f"{description} 解包失败，将继续后续任务: {exc}")

                if progress_callback is not None:
                    progress_callback(
                        entity_type,
                        finished_by_type.get(entity_type, finished_count),
                        max(totals_by_type.get(entity_type, total_tasks), 1),
                        progress_message,
                    )
    else:
        finished_count = 0
        for entity_type, entity_id, description in tasks:
            try:
                emit_running_progress(entity_type, description)
                unpack_one(entity_type, entity_id)
                progress_message = f"{description} 解包完成"
                logger.info(f"进度: {finished_count + 1}/{total_tasks} - {progress_message}。")
            except Exception as exc:  # noqa: BLE001
                failed_count += 1
                progress_message = f"{description} 解包失败"
                logger.opt(exception=show_exception).warning(f"{description} 解包失败，将继续后续任务: {exc}")

            finished_count += 1
            finished_by_type[entity_type] = finished_by_type.get(entity_type, 0) + 1
            if progress_callback is not None:
                progress_callback(
                    entity_type,
                    finished_by_type.get(entity_type, finished_count),
                    max(totals_by_type.get(entity_type, total_tasks), 1),
                    progress_message,
                )

    end_time = time.time()
    summary_message = (
        f"解包完成: {' 和 '.join(summary_parts)}，"
        f"成功 {total_tasks - failed_count} 个，失败 {failed_count} 个，"
        f"耗时 {end_time - start_time:.2f}s"
    )
    if failed_count == total_tasks:
        logger.error(summary_message)
    elif failed_count > 0:
        logger.warning(summary_message)
    else:
        logger.success(summary_message)

    reader.write_unknown_categories()
    return None


def unpack_all(  # noqa: PLR0913
    reader: DataReader,
    max_workers: int = 4,
    *,
    include_champions: bool = True,
    include_maps: bool = True,
    ctx: AppContext,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
    persisted_wem_callback: Callable[[Path], None] | None = None,
) -> None:
    """解包全部实体音频。"""
    champion_tasks = generate_champion_tasks(reader) if include_champions else []
    map_tasks = generate_map_tasks(reader) if include_maps else []
    execute_tasks(
        champion_tasks + map_tasks,
        reader,
        max_workers=max_workers,
        ctx=ctx,
        progress_callback=progress_callback,
        persisted_wem_callback=persisted_wem_callback,
    )


def unpack_champions(  # noqa: PLR0913
    reader: DataReader,
    champion_ids: list[int] | None = None,
    max_workers: int = 4,
    *,
    ctx: AppContext,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
    persisted_wem_callback: Callable[[Path], None] | None = None,
) -> None:
    """解包指定英雄音频。"""
    tasks = generate_champion_tasks(reader, champion_ids)
    execute_tasks(
        tasks,
        reader,
        max_workers=max_workers,
        ctx=ctx,
        progress_callback=progress_callback,
        persisted_wem_callback=persisted_wem_callback,
    )


def unpack_maps(  # noqa: PLR0913
    reader: DataReader,
    map_ids: list[int] | None = None,
    max_workers: int = 4,
    *,
    ctx: AppContext,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
    persisted_wem_callback: Callable[[Path], None] | None = None,
) -> None:
    """解包指定地图音频。"""
    tasks = generate_map_tasks(reader, map_ids)
    execute_tasks(
        tasks,
        reader,
        max_workers=max_workers,
        ctx=ctx,
        progress_callback=progress_callback,
        persisted_wem_callback=persisted_wem_callback,
    )
