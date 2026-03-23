"""执行中心后台任务运行器。"""

from __future__ import annotations

from time import perf_counter
from typing import TYPE_CHECKING

from loguru import logger

from lol_audio_unpack.app_context import create_app_context
from lol_audio_unpack.facade import LolAudioUnpackApp
from lol_audio_unpack.gui.task_models import ExecutionTaskResult, QueuedExecutionTask

if TYPE_CHECKING:
    from lol_audio_unpack.gui.workers import WorkerSignals


def _resolve_task_scope(task: QueuedExecutionTask) -> tuple[str, bool, bool]:
    """推导任务对应的后端目标范围。

    Args:
        task: 已入队任务。

    Returns:
        ``(target, include_champions, include_maps)`` 元组。
    """
    champion_ids = task.draft.champion_ids
    map_ids = task.draft.map_ids

    include_champions = champion_ids is None or len(champion_ids) > 0
    include_maps = map_ids is None or len(map_ids) > 0

    if champion_ids is not None and map_ids is not None:
        return "all", True, True
    if champion_ids is not None:
        return "skin", True, False
    if map_ids is not None:
        return "map", False, True
    return "all", include_champions, include_maps


def _build_runtime_overrides(task: QueuedExecutionTask) -> dict[str, str | bool]:
    """合并运行任务所需的上下文覆盖配置。

    Args:
        task: 已入队任务。

    Returns:
        可直接传给 ``create_app_context`` 的配置映射。
    """
    overrides = dict(task.draft.app_context_overrides)
    overrides["WITH_BP_VO"] = task.draft.with_bp_vo
    overrides["EXCLUDE_TYPE"] = ",".join(task.draft.exclude_types)
    return overrides


def run_execution_task(task: QueuedExecutionTask, signals: WorkerSignals) -> ExecutionTaskResult:
    """在后台线程中执行单个队列任务。

    Args:
        task: 待执行的队列任务。
        signals: 用于回传进度的 worker 信号对象。

    Returns:
        任务完成后的结果摘要。

    Raises:
        Exception: 将真实后端异常继续上抛给上层 worker。
    """
    started_at = perf_counter()
    overrides = _build_runtime_overrides(task)
    app_context = create_app_context(cli_overrides=overrides)
    app = LolAudioUnpackApp(app_context)
    options = task.draft.to_operation_options()
    target, include_champions, include_maps = _resolve_task_scope(task)
    steps = task.draft.selected_steps()
    completed_steps: list[str] = []

    try:
        for index, step_name in enumerate(steps, start=1):
            signals.progress.emit(index - 1, len(steps), f"开始{step_name}")
            logger.info(f"[执行中心] 任务 #{task.task_id} 开始{step_name}")

            if step_name == "更新数据":
                app.update(options, target=target)
            elif step_name == "音频解包":
                app.extract(
                    options,
                    include_champions=include_champions,
                    include_maps=include_maps,
                )
            elif step_name == "事件映射":
                app.mapping(
                    options,
                    include_champions=include_champions,
                    include_maps=include_maps,
                )

            completed_steps.append(step_name)
            signals.progress.emit(index, len(steps), f"{step_name}完成")

    except Exception:  # noqa: BLE001
        logger.exception(f"[执行中心] 任务 #{task.task_id} 执行失败")
        raise

    duration_seconds = perf_counter() - started_at
    summary = f"已完成：{' -> '.join(completed_steps)}（{duration_seconds:.1f}s）"
    logger.success(f"[执行中心] 任务 #{task.task_id} {summary}")
    return ExecutionTaskResult(
        completed_steps=tuple(completed_steps),
        summary=summary,
        duration_seconds=duration_seconds,
    )
