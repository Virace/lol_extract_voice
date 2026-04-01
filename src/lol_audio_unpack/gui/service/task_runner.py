"""执行中心后台任务运行器。"""

from __future__ import annotations

from time import perf_counter
from typing import TYPE_CHECKING

from loguru import logger

from lol_audio_unpack.app_context import create_app_context
from lol_audio_unpack.config_schema import SettingKey
from lol_audio_unpack.facade import LolAudioUnpackApp
from lol_audio_unpack.gui.common.packaged_remote_mode_policy import normalize_app_context_settings
from lol_audio_unpack.gui.task_models import (
    ExecutionTaskProgress,
    ExecutionTaskResult,
    QueuedExecutionTask,
)

if TYPE_CHECKING:
    from lol_audio_unpack.gui.workers import WorkerSignals


STAGE_KEY_BY_STEP_NAME = {
    "更新数据": "update",
    "音频解包": "extract",
    "事件映射": "mapping",
}
STAGE_LABEL_BY_KEY = {
    "update": "更新数据",
    "extract": "音频解包",
    "mapping": "事件映射",
}
ENTITY_SCOPE_LABEL_BY_TYPE = {
    "champion": "英雄",
    "map": "地图",
}


def _resolve_task_scope(task: QueuedExecutionTask) -> tuple[str, bool, bool]:
    """推导任务对应的后端目标范围。

    Args:
        task: 已入队任务。

    Returns:
        ``(target, include_champions, include_maps)`` 元组。
    """
    task_params = task.draft.task_params
    champion_ids = task_params.champion_ids
    map_ids = task_params.map_ids

    include_champions = champion_ids is None or len(champion_ids) > 0
    include_maps = map_ids is None or len(map_ids) > 0

    if champion_ids is not None and map_ids is not None:
        return "all", True, True
    if champion_ids is not None:
        return "skin", True, False
    if map_ids is not None:
        return "map", False, True
    return "all", include_champions, include_maps


def _build_runtime_settings(
    task: QueuedExecutionTask,
    *,
    force_bp_vo: bool = False,
) -> dict[str, str | bool]:
    """合并运行任务所需的上下文覆盖配置。

    Args:
        task: 已入队任务。
        force_bp_vo: 是否在当前阶段强制准备 BP 语音资源。

    Returns:
        可直接传给 ``create_app_context`` 的共享配置映射。
    """
    settings = task.draft.context_input.to_settings()
    settings.update(task.draft.task_params.to_runtime_overrides())
    if force_bp_vo:
        settings[SettingKey.WITH_BP_VO] = True
    return normalize_app_context_settings(settings)


def _build_scope_label(*, include_champions: bool, include_maps: bool) -> str:
    """将当前任务范围格式化为用户可读文案。"""
    scope_parts: list[str] = []
    if include_champions:
        scope_parts.append("英雄")
    if include_maps:
        scope_parts.append("地图")
    return " + ".join(scope_parts) if scope_parts else "未选择目标"


def _emit_stage_progress(  # noqa: PLR0913
    signals: WorkerSignals,
    *,
    stage_key: str,
    entity_scope_label: str,
    current: int = 0,
    total: int = 0,
    message: str = "",
    stage_finished: bool = False,
) -> None:
    """向 GUI 发出结构化阶段进度。"""
    signals.progress.emit(
        ExecutionTaskProgress(
            stage_key=stage_key,
            stage_label=STAGE_LABEL_BY_KEY.get(stage_key, stage_key),
            entity_scope_label=entity_scope_label,
            current=current,
            total=total,
            message=message,
            stage_finished=stage_finished,
        )
    )


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
    task_params = task.draft.task_params
    options = task_params.to_operation_options()
    target, include_champions, include_maps = _resolve_task_scope(task)
    task_scope_label = _build_scope_label(
        include_champions=include_champions,
        include_maps=include_maps,
    )
    steps = task_params.selected_steps()
    completed_steps: list[str] = []
    runtime_app: LolAudioUnpackApp | None = None
    runtime_settings = _build_runtime_settings(task)
    source_mode = runtime_settings.get(SettingKey.SOURCE_MODE, "local_path")

    try:
        logger.info(f"[执行中心] 任务 #{task.task_id} 开始执行: {' -> '.join(steps)}")
        logger.debug(
            f"[执行中心] 任务 #{task.task_id} 范围={task_scope_label}, "
            f"source_mode={source_mode}"
        )
        for step_name in steps:
            stage_key = STAGE_KEY_BY_STEP_NAME.get(step_name, "unknown")
            logger.info(f"[执行中心] 任务 #{task.task_id} 开始{step_name}")

            if step_name == "更新数据":
                _emit_stage_progress(
                    signals,
                    stage_key=stage_key,
                    entity_scope_label=task_scope_label,
                    current=0,
                    total=1,
                    message="正在更新基础数据…",
                )
                update_app = LolAudioUnpackApp(
                    create_app_context(
                        settings=_build_runtime_settings(task, force_bp_vo=True),
                    )
                )
                update_app.update(options, target=target)
                _emit_stage_progress(
                    signals,
                    stage_key=stage_key,
                    entity_scope_label=task_scope_label,
                    current=1,
                    total=1,
                    message="更新数据完成",
                )
            elif step_name == "音频解包":
                def emit_extract_progress(
                    entity_type: str,
                    current: int,
                    total: int,
                    message: str,
                    *,
                    resolved_stage_key: str = stage_key,
                ) -> None:
                    _emit_stage_progress(
                        signals,
                        stage_key=resolved_stage_key,
                        entity_scope_label=ENTITY_SCOPE_LABEL_BY_TYPE.get(entity_type, task_scope_label),
                        current=current,
                        total=total,
                        message=message,
                    )

                if runtime_app is None:
                    logger.debug(f"[执行中心] 任务 #{task.task_id} 创建运行时 AppContext")
                    runtime_app = LolAudioUnpackApp(
                        create_app_context(
                            settings=runtime_settings,
                        )
                    )

                _emit_stage_progress(
                    signals,
                    stage_key=stage_key,
                    entity_scope_label=task_scope_label,
                    message="正在准备解包任务…",
                )
                runtime_app.extract(
                    options,
                    include_champions=include_champions,
                    include_maps=include_maps,
                    progress_callback=emit_extract_progress,
                )
                _emit_stage_progress(
                    signals,
                    stage_key=stage_key,
                    entity_scope_label=task_scope_label,
                    current=1,
                    total=1,
                    message="音频解包阶段已结束",
                    stage_finished=True,
                )
            elif step_name == "事件映射":
                mapping_progress_seen = False

                def emit_mapping_progress(
                    entity_type: str,
                    current: int,
                    total: int,
                    message: str,
                    *,
                    resolved_stage_key: str = stage_key,
                ) -> None:
                    nonlocal mapping_progress_seen
                    mapping_progress_seen = True
                    _emit_stage_progress(
                        signals,
                        stage_key=resolved_stage_key,
                        entity_scope_label=ENTITY_SCOPE_LABEL_BY_TYPE.get(entity_type, task_scope_label),
                        current=current,
                        total=total,
                        message=message,
                    )

                if runtime_app is None:
                    logger.debug(f"[执行中心] 任务 #{task.task_id} 创建运行时 AppContext")
                    runtime_app = LolAudioUnpackApp(
                        create_app_context(
                            settings=runtime_settings,
                        )
                    )

                _emit_stage_progress(
                    signals,
                    stage_key=stage_key,
                    entity_scope_label=task_scope_label,
                    message="正在准备事件映射任务…",
                )
                runtime_app.mapping(
                    options,
                    include_champions=include_champions,
                    include_maps=include_maps,
                    progress_callback=emit_mapping_progress,
                )
                if not mapping_progress_seen:
                    logger.debug(f"[执行中心] 任务 #{task.task_id} 事件映射未返回增量进度，补发单步完成进度")
                    _emit_stage_progress(
                        signals,
                        stage_key=stage_key,
                        entity_scope_label=task_scope_label,
                        current=1,
                        total=1,
                        message="事件映射完成",
                    )

            completed_steps.append(step_name)

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
