"""收集并输出命令行执行阶段总结。"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Iterator

RUNTIME_RUN_SUMMARY_KEY = "cli_run_summary"
MAX_LOG_SAMPLES = 5
IGNORED_WARNING_PREFIXES = (
    "已启用强制更新模式",
)


@dataclass
class RunStageSummary:
    """记录单个执行阶段的告警、错误与说明信息。"""

    key: str
    label: str
    executed: bool = False
    warning_count: int = 0
    error_count: int = 0
    warning_samples: list[str] = field(default_factory=list)
    error_samples: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    debug_details: list[str] = field(default_factory=list)


@dataclass
class CliRunSummary:
    """维护命令行流程的阶段状态与可解释说明。"""

    stages: dict[str, RunStageSummary] = field(default_factory=dict)
    current_stage: str | None = None
    _lock: Lock = field(default_factory=Lock, repr=False)

    def ensure_stage(self, stage_key: str, label: str | None = None) -> RunStageSummary:
        """获取已有阶段摘要，必要时创建新阶段。

        Args:
            stage_key: 阶段唯一标识。
            label: 阶段展示名称；提供时会同步更新已存在阶段的显示名称。

        Returns:
            对应阶段的摘要对象。
        """
        with self._lock:
            stage = self.stages.get(stage_key)
            if stage is None:
                stage = RunStageSummary(key=stage_key, label=label or stage_key)
                self.stages[stage_key] = stage
            elif label:
                stage.label = label
            return stage

    @contextmanager
    def stage_context(self, stage_key: str, label: str | None = None) -> Iterator[RunStageSummary]:
        """在阶段执行期间设置当前阶段上下文。

        Args:
            stage_key: 阶段唯一标识。
            label: 阶段展示名称。

        Yields:
            当前阶段的摘要对象。
        """
        stage = self.ensure_stage(stage_key, label=label)
        previous_stage = self.current_stage
        stage.executed = True
        self.current_stage = stage_key
        try:
            yield stage
        finally:
            self.current_stage = previous_stage

    def record_log(self, level_name: str, message: str) -> None:
        """将告警或错误日志归档到当前阶段摘要。

        Args:
            level_name: 日志级别名称。
            message: 日志正文。
        """
        stage_key = self.current_stage
        if not stage_key:
            return

        normalized_level = level_name.upper()
        if normalized_level == "WARNING" and message.startswith(IGNORED_WARNING_PREFIXES):
            return
        if normalized_level not in {"WARNING", "ERROR", "CRITICAL"}:
            return

        stage = self.ensure_stage(stage_key)
        with self._lock:
            if normalized_level == "WARNING":
                stage.warning_count += 1
                _append_unique_limited(stage.warning_samples, message)
            else:
                stage.error_count += 1
                _append_unique_limited(stage.error_samples, message)

    def record_note(self, stage_key: str, message: str, *, label: str | None = None, detail: str | None = None) -> None:
        """记录阶段说明及调试细节。

        Args:
            stage_key: 阶段唯一标识。
            message: 面向用户展示的说明文字。
            label: 阶段展示名称。
            detail: 仅用于调试日志的补充细节。
        """
        stage = self.ensure_stage(stage_key, label=label)
        with self._lock:
            if message not in stage.notes:
                stage.notes.append(message)
            if detail and detail not in stage.debug_details:
                stage.debug_details.append(detail)


def _append_unique_limited(target: list[str], value: str) -> None:
    """在样本列表未超限时追加唯一值。

    Args:
        target: 目标字符串列表。
        value: 待追加的字符串。
    """
    if value in target:
        return
    if len(target) >= MAX_LOG_SAMPLES:
        return
    target.append(value)


def get_or_create_run_summary(runtime_cache: dict[str, Any]) -> CliRunSummary:
    """从运行时缓存中获取或创建执行总结对象。

    Args:
        runtime_cache: 应用上下文中的运行时缓存字典。

    Returns:
        可复用的执行总结对象。
    """
    summary = runtime_cache.get(RUNTIME_RUN_SUMMARY_KEY)
    if isinstance(summary, CliRunSummary):
        return summary

    summary = CliRunSummary()
    runtime_cache[RUNTIME_RUN_SUMMARY_KEY] = summary
    return summary


def record_runtime_note(
    runtime_cache: dict[str, Any],
    stage_key: str,
    message: str,
    *,
    label: str | None = None,
    detail: str | None = None,
) -> None:
    """向运行时总结中追加可解释说明。

    Args:
        runtime_cache: 应用上下文中的运行时缓存字典。
        stage_key: 阶段唯一标识。
        message: 面向用户展示的说明文字。
        label: 阶段展示名称。
        detail: 仅用于调试日志的补充细节。
    """
    get_or_create_run_summary(runtime_cache).record_note(stage_key, message, label=label, detail=detail)


def attach_run_summary_sink(summary: CliRunSummary) -> int:
    """挂载用于收集告警与错误日志的 loguru sink。

    Args:
        summary: 目标执行总结对象。

    Returns:
        新增 sink 的标识，可用于后续移除。
    """
    def sink(message: Any) -> None:
        record = message.record
        summary.record_log(record["level"].name, record["message"])

    return logger.add(sink, level="WARNING", catch=True)


def emit_cli_run_summary(
    summary: CliRunSummary,
    *,
    log: Any = logger,
    log_path: Path | str | None = None,
) -> None:
    """将执行总结格式化输出到日志。

    Args:
        summary: 待输出的执行总结对象。
        log: 具备 `info` 与 `debug` 方法的日志对象。
        log_path: 日志目录路径，用于提示用户查看详细信息。
    """
    executed_stages = [stage for stage in summary.stages.values() if stage.executed]
    if not executed_stages:
        return

    clean_stages = [
        stage for stage in executed_stages if stage.warning_count == 0 and stage.error_count == 0 and not stage.notes
    ]
    issue_stages = [stage for stage in executed_stages if stage.warning_count > 0 or stage.error_count > 0]
    noted_stages = [stage for stage in executed_stages if stage.notes]

    log.info("执行总结：")
    if clean_stages:
        log.info(f"无异常: {', '.join(stage.label for stage in clean_stages)}")

    if issue_stages:
        issue_items = []
        for stage in issue_stages:
            counters = []
            if stage.error_count:
                counters.append(f"错误 {stage.error_count} 条")
            if stage.warning_count:
                counters.append(f"告警 {stage.warning_count} 条")
            issue_items.append(f"{stage.label} ({'，'.join(counters)})")

        if log_path:
            issue_tail = f"详细信息请查看日志目录: {Path(log_path)}，如有异常请附日志提交 issue。"
        else:
            issue_tail = "详细信息请查看日志并在必要时附日志提交 issue。"
        log.info(f"需要关注: {'; '.join(issue_items)}。{issue_tail}")

        for stage in issue_stages:
            for sample in stage.error_samples:
                log.debug(f"{stage.label} 错误样例: {sample}")
            for sample in stage.warning_samples:
                log.debug(f"{stage.label} 告警样例: {sample}")

    for stage in noted_stages:
        for note in stage.notes:
            log.info(f"可解释差异: {stage.label} -> {note}")
        for detail in stage.debug_details:
            log.debug(f"{stage.label} 详细说明: {detail}")
