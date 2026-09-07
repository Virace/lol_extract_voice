"""统一描述实体、阶段与整轮工作流的执行结果。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lol_audio_unpack.runtime.wav.batch import WavBatchResult


class ResultStatus(str, Enum):
    """工作流各层共享的稳定结果状态。"""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


def _aggregate(statuses: Iterable[ResultStatus]) -> ResultStatus:
    """按取消优先、部分成功次之的规则聚合状态。"""
    values = tuple(statuses)
    if not values:
        return ResultStatus.SUCCESS
    if ResultStatus.CANCELLED in values:
        return ResultStatus.CANCELLED
    if ResultStatus.PARTIAL in values:
        return ResultStatus.PARTIAL
    if ResultStatus.SUCCESS in values and ResultStatus.FAILED in values:
        return ResultStatus.PARTIAL
    if all(status is ResultStatus.FAILED for status in values):
        return ResultStatus.FAILED
    return ResultStatus.SUCCESS


@dataclass(frozen=True, slots=True)
class FailureDetail:
    """记录有可靠输入身份的文件或容器失败，不把容器数当作音频数。"""

    unit: str
    source_path: str
    error_message: str
    sub_entity: str = ""
    audio_type: str = ""
    category: str = ""
    wad: str = ""
    entry_hash: str = ""
    output_path: str = ""
    error_type: str = ""
    retryable: bool = False

    @property
    def binding_key(self) -> tuple[str, str, str, str, str]:
        """返回逻辑归属与物理容器共同组成的 binding 身份。"""
        return self.sub_entity, self.audio_type, self.category, self.wad, self.entry_hash

    @property
    def key(self) -> tuple[str, ...]:
        """返回同一阶段中可跨重试关联的失败身份。"""
        return self.unit, *self.binding_key, self.source_path, self.output_path


@dataclass(frozen=True, slots=True)
class EntityResult:
    """描述一个稳定实体工作项的执行事实。

    Attributes:
        entity_type: 实体领域类型，例如 ``champion`` 或 ``map``。
        entity_id: 数字 ID 或 resource-pack 稳定 key。
        status: 实体结果状态。
        entity_name: 仅用于展示的名称或任务描述。
        error_type: 稳定异常类型名；成功时为空。
        error_message: 面向调用方的简短错误摘要；完整 traceback 只进日志。
        artifacts: 成功生成或更新的 artifact 路径字符串。
    """

    entity_type: str
    entity_id: str | int
    status: ResultStatus
    entity_name: str = ""
    error_type: str | None = None
    error_message: str | None = None
    artifacts: tuple[str, ...] = ()
    failures: tuple[FailureDetail, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", ResultStatus(self.status))
        object.__setattr__(self, "artifacts", tuple(self.artifacts))
        object.__setattr__(self, "failures", tuple(self.failures))

    @classmethod
    def from_error(
        cls,
        entity_type: str,
        entity_id: str | int,
        error: BaseException,
        *,
        entity_name: str = "",
        artifacts: Iterable[str] = (),
    ) -> EntityResult:
        """从实体异常构造不携带异常对象的失败结果。

        Args:
            entity_type: 实体领域类型。
            entity_id: 稳定数字 ID 或字符串 key。
            error: 要转换为稳定文本的原始异常。
            entity_name: 仅用于展示的名称或任务描述。
            artifacts: 异常前已成功生成的 artifact 路径。

        Returns:
            状态为 failed 的实体结果。
        """
        return cls(
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            status=ResultStatus.FAILED,
            error_type=type(error).__name__,
            error_message=str(error),
            artifacts=tuple(artifacts),
        )


@dataclass(frozen=True, slots=True)
class StageResult:
    """描述一个工作流阶段及其实体结果。

    未显式提供状态时，会从实体结果和 stage 级错误派生；空阶段是合法 success no-op。
    显式状态仅用于 WAV 等已由下层可靠汇总、但不提供逐项结果的适配边界。
    """

    stage: str
    entities: tuple[EntityResult, ...] = ()
    status: ResultStatus | None = None
    error_type: str | None = None
    error_message: str | None = None
    note: str | None = None
    reports: tuple[str, ...] = ()
    wav_batches: tuple[WavBatchResult, ...] = ()

    def __post_init__(self) -> None:
        entities = tuple(self.entities)
        object.__setattr__(self, "entities", entities)
        object.__setattr__(self, "reports", tuple(self.reports))
        object.__setattr__(self, "wav_batches", tuple(self.wav_batches))
        if self.status is not None:
            object.__setattr__(self, "status", ResultStatus(self.status))
            return

        statuses = [entity.status for entity in entities]
        if self.error_type is not None:
            statuses.append(ResultStatus.FAILED)
        object.__setattr__(self, "status", _aggregate(statuses))

    @classmethod
    def from_entities(
        cls,
        stage: str,
        entities: Iterable[EntityResult],
        *,
        note: str | None = None,
    ) -> StageResult:
        """从实体结果派生阶段状态。

        Args:
            stage: 稳定阶段 key。
            entities: 按输入顺序排列的实体结果。
            note: 可选的 no-op 或阶段说明。

        Returns:
            状态和计数均由实体结果派生的阶段结果。
        """
        return cls(stage=stage, entities=tuple(entities), note=note)

    @classmethod
    def from_error(
        cls,
        stage: str,
        error: BaseException,
        *,
        entities: Iterable[EntityResult] = (),
        note: str | None = None,
    ) -> StageResult:
        """从阶段异常构造失败或部分成功结果。

        Args:
            stage: 稳定阶段 key。
            error: 要转换为稳定文本的原始异常。
            entities: 异常前已经完成的实体结果。
            note: 可选阶段说明。

        Returns:
            无成功实体时为 failed；已有成功实体时按聚合规则为 partial。
        """
        return cls(
            stage=stage,
            entities=tuple(entities),
            error_type=type(error).__name__,
            error_message=str(error),
            note=note,
        )

    @classmethod
    def combine(
        cls,
        stage: str,
        results: Iterable[StageResult],
        *,
        note: str | None = None,
    ) -> StageResult:
        """按调用顺序合并同一逻辑阶段的多个子结果。

        Args:
            stage: 合并后的稳定阶段 key。
            results: 要合并的子阶段结果。
            note: 没有子结果时使用的说明；有子结果时追加到子说明之后。

        Returns:
            保留全部实体顺序，并从子阶段状态派生总状态的阶段结果。
        """
        children = tuple(results)
        entities = tuple(entity for result in children for entity in result.entities)
        statuses = tuple(result.status for result in children if result.status is not None)
        first_error = next((result for result in children if result.error_type is not None), None)
        notes = tuple(result.note for result in children if result.note)
        if note:
            notes += (note,)
        combined_note = "；".join(notes) or None
        return cls(
            stage=stage,
            entities=entities,
            status=_aggregate(statuses),
            error_type=first_error.error_type if first_error is not None else None,
            error_message=first_error.error_message if first_error is not None else None,
            note=combined_note,
            reports=tuple(path for result in children for path in result.reports),
            wav_batches=tuple(batch for result in children for batch in result.wav_batches),
        )

    @classmethod
    def cancelled(
        cls,
        stage: str,
        *,
        entities: Iterable[EntityResult] = (),
        note: str | None = None,
    ) -> StageResult:
        """构造取消优先的阶段结果。

        Args:
            stage: 稳定阶段 key。
            entities: 取消前已经完成的实体结果。
            note: 可选取消说明。

        Returns:
            状态为 cancelled 的阶段结果。
        """
        return cls(stage=stage, entities=tuple(entities), status=ResultStatus.CANCELLED, note=note)

    @property
    def total_count(self) -> int:
        """返回阶段实体总数。"""
        return len(self.entities)

    @property
    def success_count(self) -> int:
        """返回成功实体数。"""
        return self._count(ResultStatus.SUCCESS)

    @property
    def partial_count(self) -> int:
        """返回部分成功实体数。"""
        return self._count(ResultStatus.PARTIAL)

    @property
    def failed_count(self) -> int:
        """返回失败实体数。"""
        return self._count(ResultStatus.FAILED)

    @property
    def cancelled_count(self) -> int:
        """返回已取消实体数。"""
        return self._count(ResultStatus.CANCELLED)

    def _count(self, status: ResultStatus) -> int:
        return sum(entity.status is status for entity in self.entities)


@dataclass(frozen=True, slots=True)
class RunResult:
    """按执行顺序聚合一轮工作流的阶段结果。"""

    stages: tuple[StageResult, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "stages", tuple(self.stages))

    @property
    def status(self) -> ResultStatus:
        """从全部已执行阶段派生整轮状态。"""
        return _aggregate(stage.status for stage in self.stages if stage.status is not None)

    @property
    def stage_count(self) -> int:
        """返回已执行阶段数。"""
        return len(self.stages)

    @property
    def total_count(self) -> int:
        """返回全部阶段的实体总数。"""
        return sum(stage.total_count for stage in self.stages)

    @property
    def success_count(self) -> int:
        """返回全部阶段的成功实体数。"""
        return sum(stage.success_count for stage in self.stages)

    @property
    def partial_count(self) -> int:
        """返回全部阶段的部分成功实体数。"""
        return sum(stage.partial_count for stage in self.stages)

    @property
    def failed_count(self) -> int:
        """返回全部阶段的失败实体数。"""
        return sum(stage.failed_count for stage in self.stages)

    @property
    def cancelled_count(self) -> int:
        """返回全部阶段的已取消实体数。"""
        return sum(stage.cancelled_count for stage in self.stages)


__all__ = [
    "FailureDetail",
    "EntityResult",
    "ResultStatus",
    "RunResult",
    "StageResult",
]
