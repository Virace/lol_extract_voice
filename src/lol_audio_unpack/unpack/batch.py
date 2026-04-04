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
from lol_audio_unpack.runtime.wav import (
    JobHandle,
    ManifestRecorder,
    TranscodeCoordinator,
    TranscodeProgress,
    build_recorder,
    launch_detached,
)
from lol_audio_unpack.runtime.wav.job import build_transcode_paths
from lol_audio_unpack.utils.run_summary import record_runtime_note

from .entity import unpack_champion, unpack_map

if TYPE_CHECKING:
    from lol_audio_unpack.app_context import AppContext, WavOutputOptions


WAV_ERROR_NOTE = "已启用 WAV 转码，但内部异常导致已自动降级为仅保留 WEM。"
_WAV_SUBMIT_LOG_INTERVAL = 25
_WAV_PROGRESS_LOG_INTERVAL = 10


def _record_wav_error(
    ctx: AppContext,
    error: Exception,
    *,
    phase: str,
    show_exception: bool,
) -> str:
    """记录 WAV 转码内部异常并返回调试详情。"""
    detail = f"phase={phase}, error_type={type(error).__name__}, error={error}"
    logger.opt(exception=show_exception).warning(f"WAV 转码 {phase} 失败，已自动降级为仅保留 WEM: {error}")
    record_runtime_note(
        ctx.runtime_cache,
        "extract",
        WAV_ERROR_NOTE,
        label="音频解包",
        detail=detail,
    )
    return detail


def _count_wav_done(snapshot: TranscodeProgress) -> int:
    """返回当前已处理完成的 WAV 任务数。"""
    return snapshot.completed_wav_job_count + snapshot.failed_wav_job_count + snapshot.skipped_wav_job_count


def _format_wav_progress(snapshot: TranscodeProgress) -> str:
    """将 WAV 转码快照格式化为可读文案。"""
    counters = [
        f"已提交 {snapshot.submitted_wav_job_count}",
        f"运行中 {snapshot.running_wav_job_count}",
        f"完成 {snapshot.completed_wav_job_count}",
        f"失败 {snapshot.failed_wav_job_count}",
    ]
    if snapshot.retried_wav_job_count:
        counters.append(f"重试 {snapshot.retried_wav_job_count}")
    if snapshot.skipped_wav_job_count:
        counters.append(f"跳过 {snapshot.skipped_wav_job_count}")

        if snapshot.phase == "draining":
            prefix = "音频解包已完成，正在等待 WAV 转码收尾"
        elif snapshot.phase == "done":
            prefix = "WAV 转码已完成"
    elif snapshot.phase == "breaker_opened":
        prefix = "WAV 转码已触发熔断，后续任务将跳过"
    elif snapshot.phase == "retrying":
        prefix = "WAV 转码失败，准备重试"
    else:
        prefix = "WAV 转码进行中"
    return f"{prefix}：{'，'.join(counters)}"


def _emit_wav_fallback(
    *,
    progress_callback: Callable[[str, int, int, str], None] | None,
) -> None:
    """向上游发出 WAV 转码已降级的进度提示。"""
    if progress_callback is None:
        return
    progress_callback("wav", 1, 1, "WAV 转码不可用，已自动降级为仅保留 WEM。")


def _build_wav_progress_handler(
    *,
    progress_callback: Callable[[str, int, int, str], None] | None,
) -> Callable[[TranscodeProgress], None]:
    """构造 WAV 转码到日志/GUI 进度的桥接回调。"""
    last_logged_submitted = 0
    last_logged_processed = 0

    def handle(snapshot: TranscodeProgress) -> None:
        nonlocal last_logged_processed, last_logged_submitted

        processed = _count_wav_done(snapshot)
        total = max(snapshot.submitted_wav_job_count, 1)
        message = _format_wav_progress(snapshot)

        if progress_callback is not None:
            progress_callback("wav", processed, total, message)

        # 这里故意做日志节流：
        # GUI/日志层只需要阶段性可见性，不能让高频转码进度反向淹没主流程日志。
        should_log = False
        log_fn = logger.info
        if snapshot.phase in {"draining", "finalized"}:
            should_log = True
        elif snapshot.phase in {"breaker_opened", "retrying"}:
            should_log = True
            log_fn = logger.warning
        elif snapshot.phase == "submitted":
            submitted = snapshot.submitted_wav_job_count
            if submitted == 1 or submitted - last_logged_submitted >= _WAV_SUBMIT_LOG_INTERVAL:
                should_log = True
                last_logged_submitted = submitted
        elif snapshot.phase in {"completed", "failed"}:
            if processed in {1, snapshot.submitted_wav_job_count}:
                should_log = True
            elif processed - last_logged_processed >= _WAV_PROGRESS_LOG_INTERVAL:
                should_log = True
            if should_log:
                last_logged_processed = processed

        if should_log:
            log_fn(message)

    return handle


def execute_tasks(  # noqa: PLR0913
    tasks: list[tuple[str, int, str]],
    reader: DataReader,
    max_workers: int = 4,
    *,
    ctx: AppContext,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
    persisted_wem_callback: Callable[[Path], None] | None = None,
    wav_output: WavOutputOptions | None = None,
    detach_wav: bool = False,
    wav_job_label: str | None = None,
) -> JobHandle | None:
    """执行批量解包任务。

    Args:
        tasks: 任务元组列表 ``[(entity_type, id, description), ...]``。
        reader: 数据读取器实例。
        max_workers: 最大并发线程数。
        ctx: 运行时上下文。
        progress_callback: 每个实体处理结束后的可选进度回调。
        persisted_wem_callback: WEM 落盘后的附加回调。
        wav_output: WAV 输出配置。
        detach_wav: 是否转入后台 WAV 进程。
        wav_job_label: 后台 WAV 任务标签。

    Returns:
        detached 模式下可能返回后台进程句柄，其余情况返回 ``None``。
    """
    if not tasks:
        logger.warning("没有任何任务需要执行")
        return None

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

    logger.info(
        f"开始解包 {total_tasks} 个实体 ({' 和 '.join(summary_parts)})，"
        f"模式: {'多线程' if max_workers > 1 else '单线程'} (workers: {max_workers})"
    )

    failed_count = 0
    show_exception = bool(getattr(ctx.config, "dev_mode", False))
    wav_error_detail: str | None = None

    # 解包阶段的 WAD 缓存以整轮 batch 为单位共享，
    # 这样同一个实体/多个实体命中同一 WAD 时都不会重复打开文件句柄。
    wad_cache: dict[Path, WAD] = {}
    cache_lock = threading.Lock() if max_workers > 1 else None
    coordinator = None
    detached_wav_handle: JobHandle | None = None
    detached_manifest_recorder: ManifestRecorder | None = None
    detached_job_label = wav_job_label or f"wav-job-{int(start_time * 1000)}"
    if wav_output and wav_output.enabled:
        logger.info(
            "WAV 转码已启用：workers={}，timeout={}s，retries={}，format={}",
            wav_output.worker_count,
            wav_output.timeout_seconds,
            wav_output.max_retries,
            wav_output.format,
        )
        if detach_wav:
            try:
                detached_manifest_recorder = build_recorder(
                    ctx=ctx,
                    job_label=detached_job_label,
                )
            except Exception as exc:  # noqa: BLE001
                wav_error_detail = _record_wav_error(
                    ctx,
                    exc,
                    phase="initialize_detached_manifest",
                    show_exception=show_exception,
                )
        else:
            try:
                # 前台 coordinator 与 detached job 都必须复用同一套路径装配语义，
                # 否则 audio_root / wav_root / report_root 很容易在后续改动中再次漂移。
                transcode_paths = build_transcode_paths(ctx=ctx, version=reader.version)
                coordinator = TranscodeCoordinator(
                    options=wav_output,
                    audio_root=transcode_paths.audio_root,
                    wav_root=transcode_paths.wav_root,
                    report_root=transcode_paths.report_root,
                    progress_callback=_build_wav_progress_handler(
                        progress_callback=progress_callback,
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                wav_error_detail = _record_wav_error(
                    ctx,
                    exc,
                    phase="initialize",
                    show_exception=show_exception,
                )
                _emit_wav_fallback(progress_callback=progress_callback)

    def safe_wav_submitter(wem_path: Path) -> None:
        """安全提交 WAV 转码任务。

        Args:
            wem_path: 已成功落盘的 ``.wem`` 路径。
        """
        nonlocal wav_error_detail
        if coordinator is None or wav_error_detail is not None:
            return
        try:
            coordinator.submit(wem_path)
        except Exception as exc:  # noqa: BLE001
            wav_error_detail = _record_wav_error(
                ctx,
                exc,
                phase="submit",
                show_exception=show_exception,
            )
            _emit_wav_fallback(progress_callback=progress_callback)

    def safe_detached_wav_submitter(wem_path: Path) -> None:
        """安全记录 detached WAV 清单。

        Args:
            wem_path: 已成功落盘的 ``.wem`` 路径。
        """
        nonlocal wav_error_detail
        if detached_manifest_recorder is None or wav_error_detail is not None:
            return
        try:
            detached_manifest_recorder.record(wem_path)
        except Exception as exc:  # noqa: BLE001
            wav_error_detail = _record_wav_error(
                ctx,
                exc,
                phase="record_detached_manifest",
                show_exception=show_exception,
            )

    if detach_wav:
        wav_submitter = None if detached_manifest_recorder is None else safe_detached_wav_submitter
    else:
        wav_submitter = None if coordinator is None else safe_wav_submitter

    def unpack_one(entity_type: str, entity_id: int) -> None:
        common_kwargs: dict[str, object] = {
            "wad_cache": wad_cache,
            "cache_lock": cache_lock,
            "ctx": ctx,
            "wav_submitter": wav_submitter,
        }
        if persisted_wem_callback is not None:
            common_kwargs["persisted_wem_callback"] = persisted_wem_callback
        if entity_type == "champion":
            unpack_champion(entity_id, reader, **common_kwargs)
        elif entity_type == "map":
            unpack_map(entity_id, reader, **common_kwargs)
        else:
            raise ValueError(f"未知的实体类型: {entity_type}")

    if max_workers > 1:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_task = {
                executor.submit(unpack_one, entity_type, entity_id): (entity_type, entity_id, description)
                for entity_type, entity_id, description in tasks
            }
            finished_count = 0

            for future in as_completed(future_to_task):
                entity_type, _entity_id, description = future_to_task[future]
                finished_count += 1
                finished_by_type[entity_type] = finished_by_type.get(entity_type, 0) + 1

                try:
                    future.result()
                    progress_message = f"{description} 解包完成"
                    logger.info(f"进度: {finished_count}/{total_tasks} - {progress_message}。")
                except Exception as exc:
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
                unpack_one(entity_type, entity_id)
                progress_message = f"{description} 解包完成"
                logger.info(f"进度: {finished_count + 1}/{total_tasks} - {progress_message}。")
            except Exception as exc:
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

    transcode_summary = None
    if coordinator is not None:
        try:
            coordinator.finish_extract()
        except Exception as exc:  # noqa: BLE001
            if wav_error_detail is None:
                wav_error_detail = _record_wav_error(
                    ctx,
                    exc,
                    phase="finish_extract",
                    show_exception=show_exception,
                )
                _emit_wav_fallback(progress_callback=progress_callback)
        try:
            transcode_summary = coordinator.finish()
        except Exception as exc:  # noqa: BLE001
            if wav_error_detail is None:
                wav_error_detail = _record_wav_error(
                    ctx,
                    exc,
                    phase="finish",
                    show_exception=show_exception,
                )
                _emit_wav_fallback(progress_callback=progress_callback)
            transcode_summary = None
        if transcode_summary is not None and transcode_summary.breaker_open:
            record_runtime_note(
                ctx.runtime_cache,
                "extract",
                "已启用 WAV 转码，但因系统性失败自动降级为仅保留 WEM。",
                label="音频解包",
                detail=f"breaker_reason={transcode_summary.breaker_reason}",
            )
        if transcode_summary is not None:
            summary_message = (
                f"{summary_message}；WAV 成功 {transcode_summary.completed_wav_job_count} 个，"
                f"失败 {transcode_summary.failed_wav_job_count} 个，"
                f"跳过 {transcode_summary.skipped_wav_job_count} 个"
            )
    elif (
        detach_wav
        and detached_manifest_recorder is not None
        and wav_output is not None
        and wav_error_detail is None
    ):
        try:
            detached_wav_handle = launch_detached(
                ctx=ctx,
                wav_output=wav_output,
                manifest_recorder=detached_manifest_recorder,
                job_label=detached_job_label,
            )
        except Exception as exc:  # noqa: BLE001
            wav_error_detail = _record_wav_error(
                ctx,
                exc,
                phase="launch_detached_process",
                show_exception=show_exception,
            )
        if detached_wav_handle is not None:
            logger.info("WAV 转码已转入后台进程，主流程将继续推进。")
            summary_message = f"{summary_message}；WAV 已转入后台进程"
    if wav_error_detail is not None:
        summary_message = f"{summary_message}；WAV 转码内部异常，已降级为仅保留 WEM"

    has_wav_issue = transcode_summary is not None and (
        transcode_summary.failed_wav_job_count > 0 or transcode_summary.skipped_wav_job_count > 0
    )
    if failed_count == total_tasks:
        logger.error(summary_message)
    elif failed_count > 0 or has_wav_issue or wav_error_detail is not None:
        logger.warning(summary_message)
    else:
        logger.success(summary_message)

    reader.write_unknown_categories_to_file()
    return detached_wav_handle


def unpack_all(  # noqa: PLR0913
    reader: DataReader,
    max_workers: int = 4,
    include_champions: bool = True,
    include_maps: bool = True,
    *,
    ctx: AppContext,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
    persisted_wem_callback: Callable[[Path], None] | None = None,
    wav_output: WavOutputOptions | None = None,
    detach_wav: bool = False,
    wav_job_label: str | None = None,
) -> JobHandle | None:
    """解包全部实体音频。

    Args:
        reader: 已初始化的数据读取器。
        max_workers: 最大并发线程数。
        include_champions: 是否包含英雄。
        include_maps: 是否包含地图。
        ctx: 运行时上下文。
        progress_callback: 每个实体处理结束后的可选进度回调。
        persisted_wem_callback: WEM 落盘后的附加回调。
        wav_output: WAV 输出配置。
        detach_wav: 是否转入后台 WAV 进程。
        wav_job_label: 后台 WAV 任务标签。

    Returns:
        detached 模式下可能返回后台进程句柄，其余情况返回 ``None``。
    """
    tasks = []

    if include_champions:
        champion_tasks = generate_champion_tasks(reader, None)
        tasks.extend(champion_tasks)
        logger.debug(f"已添加 {len(champion_tasks)} 个英雄解包任务")

    if include_maps:
        map_tasks = generate_map_tasks(reader, None)
        tasks.extend(map_tasks)
        logger.debug(f"已添加 {len(map_tasks)} 个地图解包任务")

    if not tasks:
        logger.warning("没有找到任何需要解包的实体")
        return None

    return execute_tasks(
        tasks,
        reader,
        max_workers,
        ctx=ctx,
        progress_callback=progress_callback,
        persisted_wem_callback=persisted_wem_callback,
        wav_output=wav_output,
        detach_wav=detach_wav,
        wav_job_label=wav_job_label,
    )


def unpack_champions(  # noqa: PLR0913
    reader: DataReader,
    champion_ids: list[int],
    max_workers: int = 4,
    *,
    ctx: AppContext,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
    persisted_wem_callback: Callable[[Path], None] | None = None,
    wav_output: WavOutputOptions | None = None,
    detach_wav: bool = False,
    wav_job_label: str | None = None,
) -> JobHandle | None:
    """解包指定英雄音频。

    Args:
        reader: 数据读取器。
        champion_ids: 英雄 ID 列表。
        max_workers: 最大并发线程数。
        ctx: 运行时上下文。
        progress_callback: 每个实体处理结束后的可选进度回调。
        persisted_wem_callback: WEM 落盘后的附加回调。
        wav_output: WAV 输出配置。
        detach_wav: 是否转入后台 WAV 进程。
        wav_job_label: 后台 WAV 任务标签。

    Returns:
        detached 模式下可能返回后台进程句柄，其余情况返回 ``None``。
    """
    tasks = generate_champion_tasks(reader, champion_ids)
    return execute_tasks(
        tasks,
        reader,
        max_workers,
        ctx=ctx,
        progress_callback=progress_callback,
        persisted_wem_callback=persisted_wem_callback,
        wav_output=wav_output,
        detach_wav=detach_wav,
        wav_job_label=wav_job_label,
    )


def unpack_maps(  # noqa: PLR0913
    reader: DataReader,
    map_ids: list[int],
    max_workers: int = 4,
    *,
    ctx: AppContext,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
    persisted_wem_callback: Callable[[Path], None] | None = None,
    wav_output: WavOutputOptions | None = None,
    detach_wav: bool = False,
    wav_job_label: str | None = None,
) -> JobHandle | None:
    """解包指定地图音频。

    Args:
        reader: 数据读取器。
        map_ids: 地图 ID 列表。
        max_workers: 最大并发线程数。
        ctx: 运行时上下文。
        progress_callback: 每个实体处理结束后的可选进度回调。
        persisted_wem_callback: WEM 落盘后的附加回调。
        wav_output: WAV 输出配置。
        detach_wav: 是否转入后台 WAV 进程。
        wav_job_label: 后台 WAV 任务标签。

    Returns:
        detached 模式下可能返回后台进程句柄，其余情况返回 ``None``。
    """
    tasks = generate_map_tasks(reader, map_ids)
    return execute_tasks(
        tasks,
        reader,
        max_workers,
        ctx=ctx,
        progress_callback=progress_callback,
        persisted_wem_callback=persisted_wem_callback,
        wav_output=wav_output,
        detach_wav=detach_wav,
        wav_job_label=wav_job_label,
    )


# 兼容层：等全项目统一收口后再移除旧名。
execute_unpack_tasks = execute_tasks
unpack_audio_all = unpack_all
