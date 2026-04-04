"""批量事件映射调度。"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Any

from loguru import logger

from lol_audio_unpack.manager import DataReader
from lol_audio_unpack.model import generate_champion_tasks, generate_map_tasks

from . import session as mapping_session
from .entity import build_champion, build_map

if TYPE_CHECKING:
    from lol_audio_unpack.app_context import AppContext


EntityTask = tuple[str, int, str]


def _summarize_tasks(tasks: list[EntityTask]) -> tuple[list[str], dict[str, int], dict[str, int]]:
    """统计当前任务集中各实体类型的数量。

    Args:
        tasks: 当前任务列表。

    Returns:
        tuple[list[str], dict[str, int], dict[str, int]]: 摘要文案、总数和完成数。
    """

    champion_count = sum(1 for entity_type, _, _ in tasks if entity_type == "champion")
    map_count = sum(1 for entity_type, _, _ in tasks if entity_type == "map")

    summary_parts: list[str] = []
    if champion_count > 0:
        summary_parts.append(f"{champion_count} 个英雄")
    if map_count > 0:
        summary_parts.append(f"{map_count} 个地图")

    totals_by_type = {"champion": champion_count, "map": map_count}
    finished_by_type = {"champion": 0, "map": 0}
    return summary_parts, totals_by_type, finished_by_type


def _build_entity(  # noqa: PLR0913
    entity_type: str,
    entity_id: int,
    reader: DataReader,
    wwiser_manager: Any,
    integrate_data: bool,
    runtime_cache: mapping_session.RuntimeCache,
    *,
    ctx: AppContext,
) -> None:
    """执行单个实体的映射构建。

    Args:
        entity_type: 实体类型。
        entity_id: 实体 ID。
        reader: 数据读取器实例。
        wwiser_manager: 可选的 wwiser 管理器。
        integrate_data: 是否输出整合数据。
        runtime_cache: 运行时缓存。
        ctx: 运行时上下文。

    Raises:
        ValueError: 实体类型未知时抛出。
    """

    if entity_type == "champion":
        build_champion(
            entity_id,
            reader,
            wwiser_manager,
            integrate_data,
            runtime_cache=runtime_cache,
            ctx=ctx,
        )
        return
    if entity_type == "map":
        build_map(
            entity_id,
            reader,
            wwiser_manager,
            integrate_data,
            runtime_cache=runtime_cache,
            ctx=ctx,
        )
        return
    raise ValueError(f"未知的实体类型: {entity_type}")


def _emit_progress(  # noqa: PLR0913
    progress_callback: Callable[[str, int, int, str], None] | None,
    entity_type: str,
    finished_by_type: dict[str, int],
    totals_by_type: dict[str, int],
    completed_count: int,
    total_tasks: int,
    progress_message: str,
) -> None:
    """按类型回传进度信息。

    Args:
        progress_callback: 外部进度回调。
        entity_type: 当前实体类型。
        finished_by_type: 各类型已完成数。
        totals_by_type: 各类型总数。
        completed_count: 当前已完成总数。
        total_tasks: 当前总任务数。
        progress_message: 当前进度文案。
    """

    if progress_callback is None:
        return
    progress_callback(
        entity_type,
        finished_by_type.get(entity_type, completed_count),
        max(totals_by_type.get(entity_type, total_tasks), 1),
        progress_message,
    )


def execute_tasks(  # noqa: PLR0913
    tasks: list[EntityTask],
    reader: DataReader,
    max_workers: int = 4,
    integrate_data: bool = False,
    *,
    ctx: AppContext,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
) -> None:
    """执行映射任务集。

    Args:
        tasks: 任务元组列表 ``[(entity_type, id, description), ...]``。
        reader: 数据读取器实例。
        max_workers: 最大工作线程数。
        integrate_data: 是否生成整合数据。
        ctx: 运行时上下文。
        progress_callback: 每个实体完成后的可选进度回调。
    """

    if not tasks:
        logger.warning("没有任何任务需要执行")
        return

    start_time = time.time()
    total_tasks = len(tasks)
    summary_parts, totals_by_type, finished_by_type = _summarize_tasks(tasks)

    logger.info(
        f"开始构建 {total_tasks} 个实体的事件映射 ({' 和 '.join(summary_parts)})，"
        f"模式: {'多线程' if max_workers > 1 else '单线程'} (workers: {max_workers})"
    )
    logger.info(f"HIRC 后端: {mapping_session.describe_hirc_backend(ctx)}")

    failed_count = 0
    show_exception = bool(getattr(ctx.config, "dev_mode", False))
    # manager 和 runtime_cache 都按“整轮任务”复用，
    # 否则多实体并发时会重复创建 wwiser 进程态和 WAD/HIRC 缓存。
    wwiser_manager = mapping_session._create_wwiser_manager(ctx)
    runtime_cache = mapping_session.RuntimeCache(cache_lock=threading.Lock() if max_workers > 1 else None)

    if max_workers > 1:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_task = {
                executor.submit(
                    _build_entity,
                    entity_type,
                    entity_id,
                    reader,
                    wwiser_manager,
                    integrate_data,
                    runtime_cache,
                    ctx=ctx,
                ): (entity_type, description)
                for entity_type, entity_id, description in tasks
            }
            completed_count = 0
            for future in as_completed(future_to_task):
                entity_type, description = future_to_task[future]
                completed_count += 1
                finished_by_type[entity_type] = finished_by_type.get(entity_type, 0) + 1
                try:
                    future.result()
                    progress_message = f"{description} 映射完成"
                    logger.info(f"进度: {completed_count}/{total_tasks} - {progress_message}。")
                except Exception as exc:  # noqa: BLE001
                    failed_count += 1
                    progress_message = f"{description} 映射失败"
                    logger.opt(exception=show_exception).warning(f"{description} 映射失败，将继续后续任务: {exc}")
                _emit_progress(
                    progress_callback,
                    entity_type,
                    finished_by_type,
                    totals_by_type,
                    completed_count,
                    total_tasks,
                    progress_message,
                )
    else:
        completed_count = 0
        for entity_type, entity_id, description in tasks:
            try:
                _build_entity(
                    entity_type,
                    entity_id,
                    reader,
                    wwiser_manager,
                    integrate_data,
                    runtime_cache,
                    ctx=ctx,
                )
                progress_message = f"{description} 映射完成"
                completed_count += 1
                logger.info(f"进度: {completed_count}/{total_tasks} - {progress_message}。")
            except Exception as exc:  # noqa: BLE001
                failed_count += 1
                progress_message = f"{description} 映射失败"
                logger.opt(exception=show_exception).warning(f"{description} 映射失败，将继续后续任务: {exc}")
            finished_by_type[entity_type] = finished_by_type.get(entity_type, 0) + 1
            _emit_progress(
                progress_callback,
                entity_type,
                finished_by_type,
                totals_by_type,
                completed_count,
                total_tasks,
                progress_message,
            )

    duration = time.time() - start_time
    summary_message = (
        f"映射完成: {' 和 '.join(summary_parts)}，"
        f"成功 {total_tasks - failed_count} 个，失败 {failed_count} 个，"
        f"耗时 {duration:.2f}s"
    )
    if failed_count == 0:
        logger.success(summary_message)
    elif failed_count < total_tasks:
        logger.warning(summary_message)
    else:
        logger.error(summary_message)


def build_all(  # noqa: PLR0913
    reader: DataReader,
    max_workers: int = 4,
    include_champions: bool = True,
    include_maps: bool = True,
    integrate_data: bool = False,
    *,
    ctx: AppContext,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
) -> None:
    """构建所有实体的事件映射。

    Args:
        reader: 已初始化的数据读取器。
        max_workers: 最大工作线程数。
        include_champions: 是否包含英雄。
        include_maps: 是否包含地图。
        integrate_data: 是否生成整合数据。
        ctx: 运行时上下文。
        progress_callback: 每个实体完成后的可选进度回调。
    """

    tasks: list[EntityTask] = []
    if include_champions:
        champion_tasks = generate_champion_tasks(reader, None)
        tasks.extend(champion_tasks)
        logger.debug(f"已添加 {len(champion_tasks)} 个英雄映射任务")
    if include_maps:
        map_tasks = generate_map_tasks(reader, None)
        tasks.extend(map_tasks)
        logger.debug(f"已添加 {len(map_tasks)} 个地图映射任务")
    if not tasks:
        logger.warning("没有找到任何需要映射的实体")
        return

    execute_tasks(
        tasks,
        reader,
        max_workers,
        integrate_data,
        ctx=ctx,
        progress_callback=progress_callback,
    )


def build_champions(  # noqa: PLR0913
    reader: DataReader,
    champion_ids: list[int],
    max_workers: int = 4,
    integrate_data: bool = False,
    *,
    ctx: AppContext,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
) -> None:
    """构建指定英雄的事件映射。

    Args:
        reader: 数据读取器实例。
        champion_ids: 英雄 ID 列表。
        max_workers: 最大工作线程数。
        integrate_data: 是否生成整合数据。
        ctx: 运行时上下文。
        progress_callback: 每个实体完成后的可选进度回调。
    """

    execute_tasks(
        generate_champion_tasks(reader, champion_ids),
        reader,
        max_workers,
        integrate_data,
        ctx=ctx,
        progress_callback=progress_callback,
    )


def build_maps(  # noqa: PLR0913
    reader: DataReader,
    map_ids: list[int],
    max_workers: int = 4,
    integrate_data: bool = False,
    *,
    ctx: AppContext,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
) -> None:
    """构建指定地图的事件映射。

    Args:
        reader: 数据读取器实例。
        map_ids: 地图 ID 列表。
        max_workers: 最大工作线程数。
        integrate_data: 是否生成整合数据。
        ctx: 运行时上下文。
        progress_callback: 每个实体完成后的可选进度回调。
    """

    execute_tasks(
        generate_map_tasks(reader, map_ids),
        reader,
        max_workers,
        integrate_data,
        ctx=ctx,
        progress_callback=progress_callback,
    )
