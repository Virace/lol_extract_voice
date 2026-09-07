"""按可靠粒度整理任务失败，并用重试证据更新解决状态。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from lol_audio_unpack.runtime.wav.batch import WavBatchResult

from .results import EntityResult, FailureDetail, ResultStatus, RunResult


@dataclass(frozen=True, slots=True)
class TaskFailure:
    """描述详情面板中的一个失败身份，单位与重试范围保持一致。"""

    key: tuple[str, ...]
    stage: str
    unit: str
    label: str
    error: str
    source_path: str = ""
    output_path: str = ""
    entity: EntityResult | None = None
    detail: FailureDetail | None = None
    wav_batch: WavBatchResult | None = None
    resolved: bool = False

    @property
    def retry_mode(self) -> str:
        """返回能由当前证据支持的执行范围，未知完成范围只提供诊断。"""
        if self.resolved:
            return "none"
        if self.wav_batch is not None and self.unit == "file":
            return "wav_files"
        if self.stage == "extract" and self.detail is not None and self.detail.retryable:
            return "extract_bindings"
        if self.detail is not None:
            return "diagnostics"
        if self.stage in {"extract", "mapping", "update", "wav"}:
            return (
                "entity_stage"
                if self.entity is not None and self.entity.entity_type in {"champion", "map", "resource_pack"}
                else "stage"
            )
        return "diagnostics"

    @property
    def guidance(self) -> str:
        """给出证据足够的修复方向，不把未知解析失败断言为损坏或程序错误。"""
        text = self.error.casefold()
        if any(token in text for token in ("permission", "access denied", "权限", "拒绝访问")):
            return "请先确认输出目录可写、文件未被占用，再按所示范围重试。"
        if any(token in text for token in ("no space", "disk full", "空间不足", "磁盘已满")):
            return "请先清理输出磁盘空间，再重试本次失败范围。"
        if any(token in text for token in ("not found", "不存在", "不可用", "missing")):
            return "请先恢复对应输入或重新准备实体数据；不会自动下载或扩大处理范围。"
        return "原因尚未确定，请查看诊断。直接重试可能仍会失败。"


def collect_failures(result: RunResult, batches: tuple[WavBatchResult, ...] = ()) -> tuple[TaskFailure, ...]:
    """从 typed result 与本轮 WAV 报告生成精确失败行，不解析日志。"""
    issues: list[TaskFailure] = []
    for batch in batches:
        if batch.report_error:
            issues.append(
                TaskFailure(
                    ("report", batch.operation_id),
                    "report",
                    "stage",
                    "WAV 报告未保存",
                    batch.report_error,
                    output_path=str(batch.report_path),
                )
            )
        for item in batch.failures:
            relative = Path(item.source_path).relative_to(batch.scope.root).as_posix()
            issues.append(
                TaskFailure(
                    ("wav", "file", item.source_path, item.output_path),
                    "wav",
                    "file",
                    relative,
                    item.error,
                    item.source_path,
                    item.output_path,
                    wav_batch=batch,
                )
            )
        if batch.error_message:
            issues.append(
                TaskFailure(
                    ("wav", "unknown", batch.operation_id),
                    "run",
                    "unknown",
                    f"{batch.unconfirmed_count} 个文件完成状态未知"
                    if batch.unconfirmed_count
                    else "音频范围复核未完成",
                    batch.error_message,
                    str(batch.scope.root),
                    str(batch.output_root),
                    wav_batch=batch,
                )
            )
    for stage in result.stages:
        if stage.stage == "wav" and stage.wav_batches:
            continue
        for entity in stage.entities:
            if entity.status is ResultStatus.SUCCESS:
                continue
            label = entity.entity_name or f"{entity.entity_type} {entity.entity_id}"
            if entity.failures:
                for detail in entity.failures:
                    item_label = f"{label} · {detail.sub_entity} · {detail.audio_type} · {Path(detail.output_path or detail.source_path).name}"
                    issues.append(
                        TaskFailure(
                            (stage.stage, str(entity.entity_type), str(entity.entity_id), *detail.key),
                            stage.stage,
                            detail.unit,
                            item_label,
                            detail.error_message,
                            detail.source_path,
                            detail.output_path,
                            entity=entity,
                            detail=detail,
                        )
                    )
            else:
                issues.append(
                    TaskFailure(
                        (stage.stage, "entity", entity.entity_type, str(entity.entity_id)),
                        stage.stage,
                        "entity",
                        label,
                        entity.error_message or stage.note or "未提供精确失败身份，请查看诊断",
                        entity=entity,
                    )
                )
        if stage.status is not ResultStatus.SUCCESS and (stage.error_message or not stage.entities):
            issues.append(
                TaskFailure(
                    (stage.stage, "stage"),
                    stage.stage,
                    "stage",
                    stage.stage,
                    stage.error_message or stage.note or "没有可靠完成范围，请检查日志与已有产物。",
                )
            )
    return tuple(issues)


def reconcile_failures(
    previous: tuple[TaskFailure, ...],
    result: RunResult,
    batches: tuple[WavBatchResult, ...],
    attempted: frozenset[tuple[str, ...]],
) -> tuple[TaskFailure, ...]:
    """只用本次明确尝试的范围和可靠终态标记解决，保留未处理的原失败。"""
    current = {issue.key: issue for issue in collect_failures(result, batches)}
    merged: list[TaskFailure] = []
    for issue in previous:
        replacement = current.pop(issue.key, None)
        if replacement is not None:
            merged.append(replacement)
            continue
        resolved = issue.resolved
        if issue.key in attempted:
            if issue.wav_batch is not None and issue.unit == "file":
                resolved = any(
                    not batch.error_message
                    and batch.parent_id == issue.wav_batch.operation_id
                    and issue.source_path not in {item.source_path for item in batch.failures}
                    and batch.scope.contains(Path(issue.source_path).relative_to(batch.scope.root).as_posix())
                    for batch in batches
                )
            else:
                for stage in result.stages:
                    if stage.stage != issue.stage:
                        continue
                    if issue.entity is None:
                        resolved = stage.status is ResultStatus.SUCCESS
                        continue
                    entity = next(
                        (
                            item
                            for item in stage.entities
                            if item.entity_type == issue.entity.entity_type
                            and str(item.entity_id) == str(issue.entity.entity_id)
                        ),
                        None,
                    )
                    if entity is None:
                        continue
                    resolved = entity.status is ResultStatus.SUCCESS
                    if issue.detail is not None:
                        if issue.detail.unit == "file" and issue.detail.output_path in entity.artifacts:
                            resolved = True
                        elif issue.detail.unit == "container" and any(
                            item.unit == "file" and item.binding_key == issue.detail.binding_key
                            for item in entity.failures
                        ):
                            # 已经定位到容器内某个 WEM 的写入失败，证明原解析边界已通过。
                            resolved = True
                        elif (
                            issue.detail.unit == "container"
                            and entity.status is ResultStatus.PARTIAL
                            and entity.failures
                            and all(item.binding_key != issue.detail.binding_key for item in entity.failures)
                        ):
                            # 同一次限定容器重试仅在其他容器失败，当前容器已通过。
                            resolved = True
        merged.append(replace(issue, resolved=resolved))
    merged.extend(current.values())
    return tuple(merged)
