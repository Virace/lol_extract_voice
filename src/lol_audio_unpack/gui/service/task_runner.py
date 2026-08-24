"""执行中心后台任务运行器。"""

from __future__ import annotations

from dataclasses import asdict, replace
from time import perf_counter
from typing import TYPE_CHECKING

from loguru import logger

from lol_audio_unpack.app.context import create_app_context
from lol_audio_unpack.app.facade import LolAudioUnpackApp
from lol_audio_unpack.app.resource_pack import partition_special_targets
from lol_audio_unpack.app.results import ResultStatus, RunResult, StageResult
from lol_audio_unpack.app.special_content import merge_champion_ids
from lol_audio_unpack.app.targets import resolve_scope
from lol_audio_unpack.app.types import OperationOptions
from lol_audio_unpack.config import SettingKey
from lol_audio_unpack.gui.task_models import (
    ExecutionTaskProgress,
    ExecutionTaskResult,
    QueuedExecutionTask,
)

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


def _stage_has_artifacts(result: StageResult) -> bool:
    """返回阶段是否携带本轮已确认落盘的产物。"""
    return any(entity.artifacts for entity in result.entities)


def _stage_produced_output(result: StageResult) -> bool:
    """判断阶段是否能进入 GUI 的已产生产物步骤列表。"""
    if result.status not in {ResultStatus.SUCCESS, ResultStatus.PARTIAL}:
        return False
    if result.stage == "update":
        # GUI 的 update 始终是显式 force update；成功返回表示基础 artifact 已完成换代。
        if result.status is ResultStatus.SUCCESS:
            return result.note != "当前目标不需要更新。"
        return _stage_has_artifacts(result)
    return _stage_has_artifacts(result)


def _build_wav_options(options: OperationOptions, extract_result: StageResult) -> OperationOptions:
    """把 WAV 消费范围限制到本轮解包已确认落盘的实体。"""
    eligible_entities = tuple(
        entity
        for entity in extract_result.entities
        if entity.status in {ResultStatus.SUCCESS, ResultStatus.PARTIAL} and entity.artifacts
    )
    return replace(
        options,
        champion_ids=tuple(int(entity.entity_id) for entity in eligible_entities if entity.entity_type == "champion"),
        map_ids=tuple(int(entity.entity_id) for entity in eligible_entities if entity.entity_type == "map"),
        special_targets=(),
        resource_pack_wads=(),
    )


def _terminal_progress_counts(result: StageResult) -> tuple[int, int]:
    """构造不会把非 success 终态伪装成满进度的计数。"""
    total = max(result.total_count, 1)
    if result.status is ResultStatus.SUCCESS:
        return total, total
    artifact_count = sum(bool(entity.artifacts) for entity in result.entities)
    return min(artifact_count, total - 1), total


def _terminal_stage_message(result: StageResult) -> str:
    """按 typed status 构造阶段收尾文案。"""
    label = STAGE_LABEL_BY_KEY.get(result.stage, result.stage)
    if result.status is ResultStatus.SUCCESS:
        return f"{label}完成" if _stage_produced_output(result) else f"{label}无需处理"
    if result.status is ResultStatus.PARTIAL:
        return f"{label}部分完成"
    if result.status is ResultStatus.CANCELLED:
        return f"{label}已取消"
    return f"{label}失败"


def _emit_terminal_stage_progress(
    signals: WorkerSignals,
    result: StageResult,
    *,
    entity_scope_label: str,
) -> None:
    """将 typed stage result 映射为最终结构化进度。"""
    current, total = _terminal_progress_counts(result)
    _emit_stage_progress(
        signals,
        stage_key=result.stage,
        entity_scope_label=entity_scope_label,
        current=current,
        total=total,
        message=_terminal_stage_message(result),
        stage_finished=True,
    )


def _build_run_summary(
    result: RunResult,
    completed_steps: tuple[str, ...],
    duration_seconds: float,
) -> str:
    """根据权威整轮结果构造用户可观察的终态摘要。"""
    duration = f"{duration_seconds:.1f}s"
    productive_text = " -> ".join(completed_steps)
    if result.status is ResultStatus.SUCCESS:
        if productive_text:
            return f"已完成：{productive_text}（{duration}）"
        return f"执行完成：本轮没有产生新产物（{duration}）"

    count_text = (
        f"成功 {result.success_count}，部分成功 {result.partial_count}，"
        f"失败 {result.failed_count}，取消 {result.cancelled_count}"
    )
    product_text = f"已产生产物的阶段：{productive_text}" if productive_text else "本轮没有确认的新产物"
    if result.status is ResultStatus.PARTIAL:
        return f"部分完成：{product_text}；{count_text}（{duration}）"
    if result.status is ResultStatus.CANCELLED:
        return f"已取消：{product_text}；{count_text}（{duration}）"
    return f"执行失败：{product_text}；{count_text}（{duration}）"


def _log_run_result(task_id: int, result: RunResult, summary: str) -> None:
    """按 typed status 记录一次 GUI 任务终态。"""
    message = f"[执行中心] 任务 #{task_id} {summary}"
    if result.status is ResultStatus.SUCCESS:
        logger.success(message)
    elif result.status in {ResultStatus.PARTIAL, ResultStatus.CANCELLED}:
        logger.warning(message)
    else:
        logger.error(message)


def _require_stage_result(result: StageResult | None, stage_key: str) -> StageResult:
    """拒绝已选择的 GUI 阶段静默丢失后端结果。"""
    if result is None:
        raise RuntimeError(f"已选择的 {stage_key} 阶段没有返回执行结果")
    if result.stage != stage_key:
        raise RuntimeError(f"{stage_key} 阶段返回了不匹配的结果 key: {result.stage}")
    return result


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


def _validate_special_targets(task: QueuedExecutionTask) -> None:
    """在创建 AppContext 前验证特殊内容的阶段兼容边界。"""
    task_params = task.draft.task_params
    partition = partition_special_targets(task_params.special_targets)
    has_resource_pack_scope = bool(partition.resource_pack_targets or task_params.resource_pack_wads)
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
    return settings


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

    reader = runtime_app._get_reader()
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
    stage_results: list[StageResult] = []
    extract_result: StageResult | None = None
    runtime_app: LolAudioUnpackApp | None = None
    map_banks_checked = False
    runtime_settings = _build_runtime_settings(task)
    _validate_special_targets(task)

    try:
        logger.info(f"[执行中心] 任务 #{task.task_id} 开始执行: {' -> '.join(steps)}")
        logger.debug(f"[执行中心] 任务 #{task.task_id} 范围={task_scope_label}")
        logger.debug(f"[执行中心] 任务 #{task.task_id} 共享上下文快照={task.draft.context_input.to_settings()}")
        logger.debug(
            f"[执行中心] 任务 #{task.task_id} 参数快照 "
            f"task_params={asdict(task_params)}, runtime_settings={runtime_settings}, options={asdict(options)}"
        )
        for step_name in steps:
            stage_key = STAGE_KEY_BY_STEP_NAME.get(step_name, "unknown")
            stage_result: StageResult | None = None
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
                stage_result = _require_stage_result(update_app.update(options, target=target), stage_key)
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
                stage_result = _require_stage_result(
                    runtime_app.extract(
                        options,
                        include_champions=include_champions,
                        include_maps=include_maps,
                        progress_callback=emit_extract_progress,
                    ),
                    stage_key,
                )
            elif step_name == "音频转码":
                if extract_result is not None and extract_result.status is ResultStatus.FAILED:
                    logger.warning(f"[执行中心] 任务 #{task.task_id} 解包没有成功实体，跳过依赖的音频转码")
                    continue

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
                stage_result = _require_stage_result(
                    runtime_app.transcode_wav(
                        _build_wav_options(options, extract_result) if extract_result is not None else options,
                        progress_callback=emit_wav_progress,
                        job_label=f"gui-task-{task.task_id}",
                    ),
                    stage_key,
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
                stage_result = _require_stage_result(
                    runtime_app.mapping(
                        options,
                        include_champions=include_champions,
                        include_maps=include_maps,
                        progress_callback=emit_mapping_progress,
                    ),
                    stage_key,
                )
                if not mapping_progress_seen:
                    logger.debug(f"[执行中心] 任务 #{task.task_id} 事件映射未返回增量进度")

            resolved_result = _require_stage_result(stage_result, stage_key)
            stage_results.append(resolved_result)
            if resolved_result.stage == "extract":
                extract_result = resolved_result
            _emit_terminal_stage_progress(
                signals,
                resolved_result,
                entity_scope_label=task_scope_label,
            )
            if _stage_produced_output(resolved_result):
                completed_steps.append(step_name)
            if resolved_result.status is ResultStatus.CANCELLED:
                break
            if resolved_result.stage == "update" and resolved_result.status is ResultStatus.FAILED:
                break

    except Exception:  # noqa: BLE001
        logger.exception(f"[执行中心] 任务 #{task.task_id} 执行失败")
        raise

    duration_seconds = perf_counter() - started_at
    run_result = RunResult(tuple(stage_results))
    completed_step_names = tuple(completed_steps)
    summary = _build_run_summary(run_result, completed_step_names, duration_seconds)
    _log_run_result(task.task_id, run_result, summary)
    return ExecutionTaskResult(
        completed_steps=completed_step_names,
        summary=summary,
        duration_seconds=duration_seconds,
        run_result=run_result,
    )
