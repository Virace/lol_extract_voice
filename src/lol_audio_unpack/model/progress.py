"""跨核心流程共享的结构化进度合同。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ProgressEvent = Literal["started", "advanced", "finished"]


@dataclass(frozen=True, slots=True)
class OperationProgress:
    """描述一个核心操作阶段的可观察进度。

    进度只说明当前阶段已经处理的工作量，不能替代阶段结果或业务终态。

    Attributes:
        operation_key: 稳定操作 key，例如 ``update``。
        stage_key: 稳定阶段 key，例如 ``champion_banks``。
        event: 阶段生命周期事件。
        current: 已处理数量；总量未知时为 ``None``。
        total: 可测总量；未知时为 ``None``。
        entity_type: 当前实体类型。
        entity_id: 当前实体 ID。
    """

    operation_key: str
    stage_key: str
    event: ProgressEvent
    current: int | None = None
    total: int | None = None
    entity_type: str | None = None
    entity_id: str | int | None = None


__all__ = ["OperationProgress", "ProgressEvent"]
