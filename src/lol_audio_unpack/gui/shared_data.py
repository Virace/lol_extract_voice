"""定义 GUI 共享实体目录的类型化事实合同。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from lol_audio_unpack.app.results import ResultStatus, StageResult
from lol_audio_unpack.model.progress import OperationProgress, ProgressEvent


class SharedDataPhase(str, Enum):
    """共享数据状态机的稳定阶段。"""

    BLOCKED = "blocked"
    CHECKING = "checking"
    WAITING = "waiting"
    PREPARING = "preparing"
    VERIFYING = "verifying"
    READY = "ready"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SharedDataReadiness(str, Enum):
    """完整扫描派生出的目录就绪程度。"""

    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class SharedDataPrepareTrigger(str, Enum):
    """启动当前 generation 的稳定入口。"""

    INITIAL = "initial"
    CONTEXT_CHANGE = "context_change"
    MANUAL_REFRESH = "manual_refresh"
    MANUAL_RETRY = "manual_retry"


class SharedDataProblemCode(str, Enum):
    """共享数据问题的稳定分类。"""

    CONFIGURATION_REQUIRED = "configuration_required"
    CONFIGURATION_INVALID = "configuration_invalid"
    DATASET_MISSING = "dataset_missing"
    DATASET_STALE = "dataset_stale"
    DATASET_EMPTY = "dataset_empty"
    BANK_ARTIFACT_MISSING = "bank_artifact_missing"
    EVENT_ARTIFACT_MISSING = "event_artifact_missing"
    RESOURCE_SCHEMA_MISMATCH = "resource_schema_mismatch"
    RESOURCE_BINDING_INCOMPLETE = "resource_binding_incomplete"
    MAP_COMMON_MISSING = "map_common_missing"
    ARTIFACT_CORRUPT = "artifact_corrupt"
    OUTPUT_NOT_WRITABLE = "output_not_writable"
    SOURCE_UNAVAILABLE = "source_unavailable"
    UNEXPECTED = "unexpected"

    @property
    def auto_repairable(self) -> bool:
        """返回普通 update 是否可自动尝试修复该问题。"""
        return self in {
            self.DATASET_MISSING,
            self.DATASET_STALE,
            self.DATASET_EMPTY,
            self.BANK_ARTIFACT_MISSING,
            self.EVENT_ARTIFACT_MISSING,
            self.RESOURCE_SCHEMA_MISMATCH,
            self.RESOURCE_BINDING_INCOMPLETE,
            self.MAP_COMMON_MISSING,
            self.ARTIFACT_CORRUPT,
        }


@dataclass(frozen=True, slots=True)
class SharedDataFailure:
    """描述一个目录条目未能构造的稳定事实。"""

    entity_id: str
    code: SharedDataProblemCode
    message: str

    @property
    def auto_repairable(self) -> bool:
        """返回该条目是否允许触发一次普通自动更新。"""
        return self.code.auto_repairable


def _row_identity(row: dict) -> str:
    """返回普通实体或特殊内容行的稳定身份。"""
    return str(row.get("key") or row.get("id") or "")


@dataclass(frozen=True, slots=True)
class SharedDataSectionResult:
    """描述一个目录分区的期望集合、成功行与失败条目。"""

    section: str
    expected_ids: tuple[str, ...]
    rows: tuple[dict, ...] = ()
    failures: tuple[SharedDataFailure, ...] = ()
    unprepared_ids: tuple[str, ...] = ()
    required: bool = True

    @property
    def loaded_ids(self) -> tuple[str, ...]:
        """返回成功构造且具有稳定身份的行 ID。"""
        return tuple(identity for row in self.rows if (identity := _row_identity(row)))

    @property
    def expected_count(self) -> int:
        """返回权威期望条目数。"""
        return len(self.expected_ids)

    @property
    def loaded_count(self) -> int:
        """返回成功构造的唯一条目数。"""
        return len(set(self.loaded_ids))

    @property
    def failed_count(self) -> int:
        """返回扫描失败条目数。"""
        return len(self.failures)

    @property
    def unprepared_count(self) -> int:
        """返回基础目录已知但尚未准备资源的条目数。"""
        return len(self.unprepared_ids)

    @property
    def is_complete(self) -> bool:
        """返回该分区是否满足自身完整性合同。"""
        if not self.required:
            return not self.failures
        loaded_ids = self.loaded_ids
        return (
            bool(self.expected_ids)
            and not self.failures
            and len(loaded_ids) == len(set(loaded_ids))
            and set(loaded_ids) == set(self.expected_ids)
        )


@dataclass(frozen=True, slots=True)
class SharedDataProblem:
    """描述按问题码聚合后的可展示诊断。"""

    code: SharedDataProblemCode
    scope: str
    message: str
    entity_ids: tuple[str, ...] = ()
    blocking: bool = True

    @property
    def count(self) -> int:
        """返回受影响实体数量；全局问题至少计为一项。"""
        return len(self.entity_ids) or 1

    @property
    def auto_repairable(self) -> bool:
        """返回该聚合问题是否允许自动修复。"""
        return self.code.auto_repairable


@dataclass(frozen=True, slots=True)
class SharedDataSummary:
    """提供首页与页面共享的稳定目录计数。"""

    champion_expected: int
    champion_loaded: int
    champion_failed: int
    map_expected: int
    map_loaded: int
    map_failed: int
    special_discovered: int
    special_prepared: int
    special_unprepared: int

    @classmethod
    def from_sections(
        cls,
        champions: SharedDataSectionResult,
        maps: SharedDataSectionResult,
        special: SharedDataSectionResult,
    ) -> SharedDataSummary:
        """从三个目录分区派生不可漂移的计数摘要。"""
        return cls(
            champion_expected=champions.expected_count,
            champion_loaded=champions.loaded_count,
            champion_failed=champions.failed_count,
            map_expected=maps.expected_count,
            map_loaded=maps.loaded_count,
            map_failed=maps.failed_count,
            special_discovered=special.expected_count,
            special_prepared=max(0, special.loaded_count - special.unprepared_count),
            special_unprepared=special.unprepared_count,
        )


@dataclass(frozen=True, slots=True)
class SharedDataProgress:
    """描述一个 generation 内完整目录扫描的可观察进度。"""

    generation: int
    stage_key: str
    event: ProgressEvent
    current: int | None = None
    total: int | None = None
    entity_type: str | None = None
    entity_id: str | None = None


@dataclass(frozen=True, slots=True)
class SharedDataScanResult:
    """描述同一上下文与 generation 的原子目录扫描快照。"""

    generation: int
    version: str
    champions: SharedDataSectionResult
    maps: SharedDataSectionResult
    special: SharedDataSectionResult
    problems: tuple[SharedDataProblem, ...] = ()

    @property
    def summary(self) -> SharedDataSummary:
        """返回从三个分区派生的目录计数。"""
        return SharedDataSummary.from_sections(self.champions, self.maps, self.special)

    @property
    def blocking_problems(self) -> tuple[SharedDataProblem, ...]:
        """返回会阻断新任务的问题。"""
        return tuple(problem for problem in self.problems if problem.blocking)

    @property
    def all_blocking_problems_repairable(self) -> bool:
        """返回当前阻断问题是否都允许自动修复。"""
        return bool(self.blocking_problems) and all(problem.auto_repairable for problem in self.blocking_problems)

    @property
    def readiness(self) -> SharedDataReadiness:
        """按必需目录与全局问题派生最终扫描真相。"""
        fatal_codes = {
            SharedDataProblemCode.CONFIGURATION_REQUIRED,
            SharedDataProblemCode.CONFIGURATION_INVALID,
            SharedDataProblemCode.DATASET_MISSING,
            SharedDataProblemCode.DATASET_STALE,
            SharedDataProblemCode.DATASET_EMPTY,
            SharedDataProblemCode.MAP_COMMON_MISSING,
            SharedDataProblemCode.OUTPUT_NOT_WRITABLE,
            SharedDataProblemCode.SOURCE_UNAVAILABLE,
        }
        if any(problem.blocking and problem.scope in {"context", "dataset"} for problem in self.problems):
            return SharedDataReadiness.FAILED
        if any(problem.blocking and problem.code in fatal_codes for problem in self.problems):
            return SharedDataReadiness.FAILED
        if self.champions.is_complete and self.maps.is_complete:
            return SharedDataReadiness.COMPLETE
        if self.champions.loaded_count == 0 or self.maps.loaded_count == 0:
            return SharedDataReadiness.FAILED
        return SharedDataReadiness.PARTIAL


@dataclass(frozen=True, slots=True)
class SharedDataRepairScope:
    """描述一次共享数据准备需要更新的最小普通实体范围。"""

    full: bool
    champion_ids: tuple[int, ...] = ()
    map_ids: tuple[int, ...] = ()

    @classmethod
    def from_scan(cls, scan: SharedDataScanResult) -> SharedDataRepairScope:
        """从扫描证据构造完整或逐实体修复范围。"""
        full_codes = {
            SharedDataProblemCode.DATASET_MISSING,
            SharedDataProblemCode.DATASET_STALE,
            SharedDataProblemCode.DATASET_EMPTY,
            SharedDataProblemCode.MAP_COMMON_MISSING,
        }
        if any(problem.blocking and problem.code in full_codes for problem in scan.problems):
            return cls(full=True)

        champion_ids: list[int] = []
        map_ids: list[int] = []
        for section, target in ((scan.champions, champion_ids), (scan.maps, map_ids)):
            for failure in section.failures:
                if not failure.entity_id.isdigit():
                    return cls(full=True)
                target.append(int(failure.entity_id))
        if not champion_ids and not map_ids:
            return cls(full=True)
        return cls(
            full=False,
            champion_ids=tuple(dict.fromkeys(champion_ids)),
            map_ids=tuple(dict.fromkeys(map_ids)),
        )


@dataclass(frozen=True, slots=True)
class SharedDataPreparationResult:
    """保留一次后台准备的 generation、范围与权威阶段结果。"""

    generation: int
    scope: SharedDataRepairScope
    stage_result: StageResult


@dataclass(frozen=True, slots=True)
class SharedDataState:
    """共享目录控制器发布给所有页面的单一状态快照。"""

    phase: SharedDataPhase
    generation: int
    summary: SharedDataSummary | None = None
    progress: SharedDataProgress | OperationProgress | None = None
    problem: SharedDataProblem | None = None
    prepare_attempted: bool = False
    prepare_trigger: SharedDataPrepareTrigger = SharedDataPrepareTrigger.INITIAL
    scan: SharedDataScanResult | None = None
    preparation: SharedDataPreparationResult | None = None

    @property
    def active(self) -> bool:
        """返回当前阶段是否仍有共享后台流程在运行。"""
        return self.phase in {
            SharedDataPhase.CHECKING,
            SharedDataPhase.PREPARING,
            SharedDataPhase.VERIFYING,
        }

    @property
    def blocks_new_tasks(self) -> bool:
        """返回当前状态是否阻止创建新任务。"""
        return self.phase is not SharedDataPhase.READY

    @property
    def status_role(self) -> str:
        """返回供视图选择图标与语义色的稳定角色。"""
        if self.phase is SharedDataPhase.READY:
            return "success"
        if self.phase in {SharedDataPhase.PARTIAL, SharedDataPhase.BLOCKED, SharedDataPhase.CANCELLED}:
            return "caution"
        if self.phase is SharedDataPhase.FAILED:
            return "critical"
        return "info"

    @property
    def prepare_status(self) -> ResultStatus | None:
        """返回最近准备结果状态；未准备时为空。"""
        return self.preparation.stage_result.status if self.preparation is not None else None


__all__ = [
    "SharedDataFailure",
    "SharedDataPhase",
    "SharedDataPreparationResult",
    "SharedDataPrepareTrigger",
    "SharedDataProblem",
    "SharedDataProblemCode",
    "SharedDataProgress",
    "SharedDataReadiness",
    "SharedDataRepairScope",
    "SharedDataScanResult",
    "SharedDataSectionResult",
    "SharedDataState",
    "SharedDataSummary",
]
