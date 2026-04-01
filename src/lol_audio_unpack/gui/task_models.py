"""执行中心任务模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from lol_audio_unpack.app_context import OperationOptions
from lol_audio_unpack.config_schema import SettingKey

TASK_STATUS_WAITING = "等待中"
TASK_STATUS_RUNNING = "运行中"
TASK_STATUS_COMPLETED = "已完成"
TASK_STATUS_FAILED = "失败"
TASK_STATUS_CANCELLED = "已取消"


@dataclass(slots=True, frozen=True)
class AppContextInputSnapshot:
    """任务创建时记录的共享上下文输入快照。

    Args:
        settings: 创建 ``AppContext`` 时需要使用的共享输入配置。
    """

    settings: tuple[tuple[str, str | bool], ...] = ()

    def to_settings(self) -> dict[str, str | bool]:
        """转换为 ``create_app_context`` 可直接消费的共享配置。"""
        return dict(self.settings)


@dataclass(slots=True, frozen=True)
class ExecutionTaskParamsSnapshot:
    """任务创建时记录的单次执行参数快照。

    Args:
        champion_ids: 目标英雄 ID；为空时表示不限制英雄范围。
        map_ids: 目标地图 ID；为空时表示不限制地图范围。
        run_update: 是否在执行前先跑更新流程。
        run_extract: 是否执行音频解包。
        run_mapping: 是否执行事件映射。
        max_workers: 后端执行时使用的最大并发数。
        with_bp_vo: 是否包含 BP 语音。
        exclude_types: 需要排除的音频类型。
        integrate_data: 是否在映射阶段生成整合数据文件。
    """

    champion_ids: tuple[int, ...] | None = None
    map_ids: tuple[int, ...] | None = None
    run_update: bool = False
    run_extract: bool = True
    run_mapping: bool = True
    max_workers: int = 4
    with_bp_vo: bool = True
    exclude_types: tuple[str, ...] = ("SFX", "MUSIC")
    integrate_data: bool = True

    def selected_steps(self) -> tuple[str, ...]:
        """返回当前任务参数实际勾选的执行步骤。

        Returns:
            按执行顺序排列的步骤名称元组。
        """
        steps: list[str] = []
        if self.run_update:
            steps.append("更新数据")
        if self.run_extract:
            steps.append("音频解包")
        if self.run_mapping:
            steps.append("事件映射")
        return tuple(steps)

    def to_operation_options(self) -> OperationOptions:
        """转换为后端门面可直接消费的 ``OperationOptions``。

        Returns:
            基于当前任务参数构造的操作选项对象。
        """
        return OperationOptions(
            max_workers=self.max_workers,
            force_update=self.run_update,
            process_events=True,
            integrate_data=self.integrate_data,
            champion_ids=self.champion_ids,
            map_ids=self.map_ids,
        )

    def to_runtime_overrides(self) -> dict[str, str | bool]:
        """构造只属于单次任务的运行时覆盖配置。"""
        return {
            SettingKey.WITH_BP_VO: self.with_bp_vo,
            SettingKey.EXCLUDE_TYPE: ",".join(self.exclude_types),
        }


@dataclass(slots=True, frozen=True)
class ExecutionTaskDraft:
    """执行中心中的任务草稿快照。

    Args:
        source: 任务来源标识，例如 ``overview_selection`` 或 ``manual_input``。
        source_summary: 创建任务时展示给用户的来源摘要。
        context_input: 创建任务当时的共享上下文输入快照。
        task_params: 创建任务当时的单次任务参数快照。
    """

    source: str
    source_summary: str
    context_input: AppContextInputSnapshot = field(default_factory=AppContextInputSnapshot)
    task_params: ExecutionTaskParamsSnapshot = field(default_factory=ExecutionTaskParamsSnapshot)


@dataclass(slots=True, frozen=True)
class ExecutionTaskProgress:
    """执行中心中当前阶段的结构化进度快照。

    Args:
        stage_key: 阶段标识，例如 ``extract`` 或 ``mapping``。
        stage_label: 展示给用户的阶段名称。
        entity_scope_label: 当前正在推进的实体范围，例如 ``英雄`` 或 ``地图``。
        current: 当前阶段内已完成的实体数量。
        total: 当前阶段内的实体总数。
        message: 当前进度提示文案。
        stage_finished: 当前阶段是否已经收尾完成。
    """

    stage_key: str
    stage_label: str
    entity_scope_label: str = ""
    current: int = 0
    total: int = 0
    message: str = ""
    stage_finished: bool = False


@dataclass(slots=True, frozen=True)
class QueuedExecutionTask:
    """已经进入执行中心队列的任务实体。

    Args:
        task_id: 队列内的稳定任务编号。
        draft: 任务创建时的草稿快照。
        summary: 队列展示摘要。
        status: 当前任务状态。
        created_at: 创建时间。
        started_at: 实际启动时间。
        finished_at: 实际结束时间。
        progress_current: 当前进度计数。
        progress_total: 总进度计数。
        progress_message: 当前进度提示文案。
        progress_detail: 当前阶段的结构化进度快照。
        result_summary: 成功执行后的结果摘要。
        error_message: 失败时的错误摘要。
    """

    task_id: int
    draft: ExecutionTaskDraft
    summary: str
    status: str = TASK_STATUS_WAITING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    progress_current: int = 0
    progress_total: int = 0
    progress_message: str = ""
    progress_detail: ExecutionTaskProgress | None = None
    result_summary: str = ""
    error_message: str = ""


@dataclass(slots=True, frozen=True)
class ExecutionTaskResult:
    """后台任务完成后的结果摘要。

    Args:
        completed_steps: 已成功完成的步骤名称。
        summary: 展示给用户的完成摘要。
        duration_seconds: 本次任务耗时。
    """

    completed_steps: tuple[str, ...]
    summary: str
    duration_seconds: float


@dataclass(slots=True, frozen=True)
class OutputStateRefreshRequest:
    """任务完成后用于刷新 GUI 实体状态的请求。"""

    champion_ids: tuple[str, ...] = ()
    map_ids: tuple[str, ...] = ()
    requires_full_refresh: bool = False

    def has_incremental_targets(self) -> bool:
        """返回当前请求是否包含可增量刷新的实体目标。"""
        return bool(self.champion_ids or self.map_ids)
