"""执行中心后台任务运行器。"""

from __future__ import annotations

from dataclasses import asdict
from time import perf_counter
from typing import TYPE_CHECKING

from loguru import logger

from lol_audio_unpack.app.context import create_app_context
from lol_audio_unpack.app.facade import LolAudioUnpackApp
from lol_audio_unpack.app.resource_pack import partition_special_targets
from lol_audio_unpack.app.special_content import (
    is_special_content_supported,
    merge_champion_ids,
)
from lol_audio_unpack.app.targets import resolve_scope
from lol_audio_unpack.app.types import OperationOptions
from lol_audio_unpack.config import SettingKey
from lol_audio_unpack.gui.common.remote_mode_policy import normalize_app_context_settings
from lol_audio_unpack.gui.task_models import (
    ExecutionTaskProgress,
    ExecutionTaskResult,
    QueuedExecutionTask,
)
from lol_audio_unpack.manager import DataReader

if TYPE_CHECKING:
    from lol_audio_unpack.gui.workers import WorkerSignals


STAGE_KEY_BY_STEP_NAME = {
    "前置强制更新": "update",
    "音频解包": "extract",
    "音频转码": "wav",
    "事件映射": "mapping",
}
STAGE_LABEL_BY_KEY = {
    "update": "前置强制更新",
    "extract": "音频解包",
    "wav": "音频转码",
    "mapping": "事件映射",
}
ENTITY_SCOPE_LABEL_BY_TYPE = {
    "champion": "英雄",
    "map": "地图",
    "resource_pack": "历史资源包",
    "wav": "音频转码",
}


def _resolve_task_scope(task: QueuedExecutionTask) -> tuple[str, bool, bool, bool]:
    """推导任务对应的后端目标范围。

    Args:
        task: 已入队任务。

    Returns:
        ``(target, include_champions, include_maps, include_resource_packs)`` 元组。
    """
    task_params = task.draft.task_params
    partition = partition_special_targets(task_params.special_targets)
    target, include_champions, include_maps = resolve_scope(
        champion_ids=merge_champion_ids(task_params.champion_ids, partition.champion_targets),
        map_ids=task_params.map_ids,
    )
    include_resource_packs = bool(partition.resource_pack_targets or task_params.resource_pack_wads)
    if (
        include_resource_packs
        and task_params.champion_ids is None
        and not partition.champion_targets
        and task_params.map_ids is None
    ):
        # resource pack 由 app facade 独立消费，不能因空的普通目标退化为全量英雄/地图。
        include_champions = False
        include_maps = False
    return target, include_champions, include_maps, include_resource_packs


def _resolve_task_options(task: QueuedExecutionTask) -> OperationOptions:
    """保留异构 special target，由应用门面按冻结合同分区。"""
    return task.draft.task_params.to_operation_options()


def _ensure_special_targets_supported(task: QueuedExecutionTask, source_mode: object) -> None:
    """在创建任何 AppContext 前拒绝远端特殊内容任务。"""
    task_params = task.draft.task_params
    if task_params.special_targets and not is_special_content_supported(source_mode):
        raise ValueError("特殊内容仅支持本地客户端资源。")
    partition = partition_special_targets(task_params.special_targets)
    has_resource_pack_scope = bool(partition.resource_pack_targets or task_params.resource_pack_wads)
    if has_resource_pack_scope and not is_special_content_supported(source_mode):
        raise ValueError("资源包发现仅支持本地客户端资源。")
    if has_resource_pack_scope and task_params.wav_enabled:
        raise ValueError("resource pack 当前不支持 WAV 转码；请先只执行 extract 或 mapping。")


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


def _build_scope_label(
    *,
    include_champions: bool,
    include_maps: bool,
    include_resource_packs: bool,
) -> str:
    """将当前任务范围格式化为用户可读文案。"""
    scope_parts: list[str] = []
    if include_champions:
        scope_parts.append("英雄")
    if include_maps:
        scope_parts.append("地图")
    if include_resource_packs:
        scope_parts.append("历史资源包")
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


def _ensure_map_banks_ready(
    runtime_app: LolAudioUnpackApp,
    task: QueuedExecutionTask,
    *,
    include_maps: bool,
) -> None:
    """在执行地图任务前确认地图 banks 已完成生成。

    Args:
        runtime_app: 当前任务使用的运行时门面。
        task: 已入队任务。
        include_maps: 当前任务范围是否包含地图。

    Raises:
        RuntimeError: 地图基础 banks 缺失时抛出，避免静默跳过地图输出。
    """
    if not include_maps:
        return

    ctx = getattr(runtime_app, "ctx", None)
    if ctx is None:
        return

    reader = DataReader(ctx=ctx)
    map_ids = task.draft.task_params.map_ids
    target_ids = (
        tuple(int(map_id) for map_id in map_ids)
        if map_ids is not None
        else tuple(int(map_data["id"]) for map_data in reader.get_maps() if map_data.get("id") is not None)
    )
    missing_ids = [map_id for map_id in target_ids if not reader.get_map_banks(map_id)]
    if not missing_ids:
        return

    raise RuntimeError(
        f"地图基础数据仍未准备完成，缺少地图 banks: {missing_ids[:10]}。请等待后台数据准备完成后再创建任务。"
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
    options = _resolve_task_options(task)
    target, include_champions, include_maps, include_resource_packs = _resolve_task_scope(task)
    task_scope_label = _build_scope_label(
        include_champions=include_champions,
        include_maps=include_maps,
        include_resource_packs=include_resource_packs,
    )
    steps = task_params.selected_steps()
    completed_steps: list[str] = []
    runtime_app: LolAudioUnpackApp | None = None
    map_banks_checked = False
    runtime_settings = _build_runtime_settings(task)
    source_mode = runtime_settings.get(SettingKey.SOURCE_MODE, "local_path")
    _ensure_special_targets_supported(task, source_mode)

    try:
        logger.info(f"[执行中心] 任务 #{task.task_id} 开始执行: {' -> '.join(steps)}")
        logger.debug(f"[执行中心] 任务 #{task.task_id} 范围={task_scope_label}, source_mode={source_mode}")
        logger.debug(f"[执行中心] 任务 #{task.task_id} 共享上下文快照={task.draft.context_input.to_settings()}")
        logger.debug(
            f"[执行中心] 任务 #{task.task_id} 参数快照 "
            f"task_params={asdict(task_params)}, runtime_settings={runtime_settings}, options={asdict(options)}"
        )
        for step_name in steps:
            stage_key = STAGE_KEY_BY_STEP_NAME.get(step_name, "unknown")
            logger.info(f"[执行中心] 任务 #{task.task_id} 开始{step_name}")

            if step_name == "前置强制更新":
                _emit_stage_progress(
                    signals,
                    stage_key=stage_key,
                    entity_scope_label=task_scope_label,
                    current=0,
                    total=1,
                    message="正在强制刷新基础数据…",
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
                    message="基础数据刷新完成",
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
                if not map_banks_checked:
                    _ensure_map_banks_ready(runtime_app, task, include_maps=include_maps)
                    map_banks_checked = True

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
            elif step_name == "音频转码":

                def emit_wav_progress(
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
                    message="正在准备音频转码…",
                )
                runtime_app.transcode_wav(
                    options,
                    progress_callback=emit_wav_progress,
                    job_label=f"gui-task-{task.task_id}",
                )
                _emit_stage_progress(
                    signals,
                    stage_key=stage_key,
                    entity_scope_label=task_scope_label,
                    current=1,
                    total=1,
                    message="音频转码完成",
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
                if not map_banks_checked:
                    _ensure_map_banks_ready(runtime_app, task, include_maps=include_maps)
                    map_banks_checked = True

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
