"""为已有执行器构造分阶段的失败重试输入，不创建等待队列。"""

from __future__ import annotations

from dataclasses import replace

from lol_audio_unpack.app.failures import TaskFailure
from lol_audio_unpack.gui.task_models import ExecutionRetryStage, ExecutionTaskParamsSnapshot

_STAGE_LABELS = {"update": "更新", "extract": "解包", "mapping": "映射", "wav": "音频转码"}


def _params(
    original: ExecutionTaskParamsSnapshot, stage: str, issues: tuple[TaskFailure, ...], *, full: bool = False
) -> ExecutionTaskParamsSnapshot:
    params = replace(
        original,
        run_update=stage == "update",
        run_extract=stage == "extract",
        run_mapping=stage == "mapping",
        wav_enabled=stage == "wav",
    )
    if full:
        return params
    entities = tuple(issue.entity for issue in issues if issue.entity is not None)
    return replace(
        params,
        champion_ids=tuple(
            dict.fromkeys(int(entity.entity_id) for entity in entities if entity.entity_type == "champion")
        ),
        map_ids=tuple(dict.fromkeys(int(entity.entity_id) for entity in entities if entity.entity_type == "map")),
        special_targets=tuple(
            dict.fromkeys(str(entity.entity_id) for entity in entities if entity.entity_type == "resource_pack")
        ),
        resource_pack_wads=original.resource_pack_wads
        if any(entity.entity_type == "resource_pack" for entity in entities)
        else (),
    )


def build_retry_stages(
    original: ExecutionTaskParamsSnapshot, issues: tuple[TaskFailure, ...]
) -> tuple[ExecutionRetryStage, ...]:
    """为每个阶段保留独立目标；精确文件不会退化为整个实体重跑。"""
    plan: list[ExecutionRetryStage] = []
    active = tuple(issue for issue in issues if issue.retry_mode not in {"none", "diagnostics"})
    for stage in ("update", "extract", "wav", "mapping"):
        selected = tuple(issue for issue in active if issue.stage == stage)
        if not selected:
            continue
        if any(issue.retry_mode == "stage" for issue in selected):
            plan.append(
                ExecutionRetryStage(
                    f"按原任务范围重新执行{_STAGE_LABELS[stage]}阶段", _params(original, stage, selected, full=True)
                )
            )
            continue
        if stage == "wav":
            batches = {}
            for issue in selected:
                if issue.wav_batch is None:
                    continue
                batches[issue.wav_batch.operation_id] = issue.wav_batch
            selected_keys = {(issue.source_path, issue.output_path) for issue in selected}
            limited = tuple(
                replace(
                    batch,
                    failures=tuple(
                        item for item in batch.failures if (item.source_path, item.output_path) in selected_keys
                    ),
                    failed_count=sum((item.source_path, item.output_path) in selected_keys for item in batch.failures),
                )
                for batch in batches.values()
            )
            plan.append(
                ExecutionRetryStage(
                    f"仅重试 {sum(batch.failed_count for batch in limited)} 个 WAV 失败文件（替换失败输出）",
                    _params(original, stage, selected),
                    wav_batches=limited,
                )
            )
            continue
        precise = tuple(issue for issue in selected if issue.retry_mode == "extract_bindings")
        coarse = tuple(issue for issue in selected if issue.retry_mode == "entity_stage")
        if precise:
            entities = {}
            for issue in precise:
                entities[(issue.entity.entity_type, str(issue.entity.entity_id))] = issue.entity
            limited_entities = tuple(
                replace(
                    entity,
                    failures=tuple(
                        issue.detail
                        for issue in precise
                        if issue.entity.entity_type == entity.entity_type
                        and str(issue.entity.entity_id) == str(entity.entity_id)
                        and issue.detail is not None
                    ),
                )
                for entity in entities.values()
            )
            containers = len(
                {(issue.entity.entity_type, str(issue.entity.entity_id), issue.detail.binding_key) for issue in precise}
            )
            files = sum(issue.unit == "file" for issue in precise)
            plan.append(
                ExecutionRetryStage(
                    f"重读 {containers} 个容器"
                    + (f"，其中 {files} 个 WEM 仅补写失败文件" if files else "；受影响音频数未知"),
                    _params(original, stage, precise),
                    extract_entities=limited_entities,
                )
            )
        if coarse:
            plan.append(
                ExecutionRetryStage(
                    f"重新执行 {len(coarse)} 个失败对象的完整{_STAGE_LABELS[stage]}阶段",
                    _params(original, stage, coarse),
                )
            )
    return tuple(plan)
