"""把共享数据事实快照转换为一致的 GUI 展示语义。"""

from __future__ import annotations

from dataclasses import dataclass

from lol_audio_unpack.gui.shared_data import (
    SharedDataPhase,
    SharedDataProblemCode,
    SharedDataState,
)


@dataclass(frozen=True, slots=True)
class SharedDataDisplay:
    """描述所有页面共同使用的共享数据展示快照。

    Attributes:
        status_text: 主状态文案。
        card_text: 紧凑卡片文案。
        detail_text: 原因、阶段或计数说明。
        status_role: 稳定语义色角色。
        task_action_text: 执行中心主按钮文案。
        task_block_reason: 新任务被阻断时的原因。
        progress_text: 当前可观察进度文案。
        progress_current: 当前阶段已完成数量。
        progress_total: 当前阶段可测总量。
        action_key: 恢复或导航动作的稳定 key。
        action_text: 恢复或导航按钮文案。
    """

    status_text: str
    card_text: str
    detail_text: str
    status_role: str
    task_action_text: str
    task_block_reason: str
    progress_text: str
    progress_current: int | None
    progress_total: int | None
    action_key: str | None
    action_text: str

    @property
    def has_determinate_progress(self) -> bool:
        """返回当前快照是否包含可测量的有效总量。

        Returns:
            bool: current 与有效 total 同时存在时为 ``True``。
        """
        return self.progress_current is not None and self.progress_total is not None and self.progress_total > 0


_STAGE_LABELS = {
    "data": "基础数据",
    "champion_banks": "英雄数据",
    "champions": "英雄数据",
    "map_banks": "地图数据",
    "maps": "地图数据",
    "special": "特殊内容",
}


def _summary_text(state: SharedDataState) -> str:
    """从权威扫描摘要生成动态英雄与地图计数。"""
    summary = state.summary
    if summary is None:
        return ""
    return (
        f"英雄 {summary.champion_loaded}/{summary.champion_expected}，地图 {summary.map_loaded}/{summary.map_expected}"
    )


def _progress_parts(state: SharedDataState) -> tuple[str, int | None, int | None]:
    """返回当前进度的阶段文案与可测量计数。"""
    progress = state.progress
    if progress is None:
        return "", None, None
    stage_label = _STAGE_LABELS.get(progress.stage_key, "实体数据")
    current = progress.current
    total = progress.total
    if current is None or total is None or total <= 0:
        return stage_label, None, None
    normalized_current = min(max(current, 0), total)
    return f"{stage_label} · {normalized_current}/{total}", normalized_current, total


def _recovery_action(state: SharedDataState) -> tuple[str | None, str]:
    """按稳定问题码选择主恢复动作。"""
    if state.phase is SharedDataPhase.READY:
        return "view_overview", "查看实体总览"
    if state.phase is SharedDataPhase.WAITING:
        return "view_execution", "查看执行中心"
    if state.phase in {SharedDataPhase.CHECKING, SharedDataPhase.PREPARING, SharedDataPhase.VERIFYING}:
        return None, ""

    problem_code = state.problem.code if state.problem is not None else None
    if problem_code in {
        SharedDataProblemCode.CONFIGURATION_REQUIRED,
        SharedDataProblemCode.CONFIGURATION_INVALID,
        SharedDataProblemCode.OUTPUT_NOT_WRITABLE,
    }:
        return "open_settings", "打开全局设置"
    if state.prepare_attempted and problem_code is not None and problem_code.auto_repairable:
        return "regenerate", "重新生成实体数据"
    return "retry", "重试更新"


def describe_shared_data_state(state: SharedDataState) -> SharedDataDisplay:  # noqa: PLR0911
    """把类型化共享状态投影为页面共用文案与动作。

    Args:
        state: 控制器发布的当前 generation 状态。

    Returns:
        SharedDataDisplay: 页面可直接消费的统一展示快照。
    """
    summary_text = _summary_text(state)
    progress_text, progress_current, progress_total = _progress_parts(state)
    action_key, action_text = _recovery_action(state)
    problem_text = state.problem.message if state.problem is not None else ""

    if state.phase is SharedDataPhase.BLOCKED:
        detail = problem_text or "配置有效目录后会自动加载英雄和地图列表。"
        return SharedDataDisplay(
            "需要配置共享数据",
            "等待配置",
            detail,
            state.status_role,
            "创建任务",
            detail,
            "",
            None,
            None,
            action_key,
            action_text,
        )
    if state.phase is SharedDataPhase.CHECKING:
        detail = f"正在检查{progress_text}" if progress_text else "正在读取当前版本与结构化数据。"
        return SharedDataDisplay(
            "正在检查实体数据…",
            "检查中…",
            detail,
            state.status_role,
            "准备数据中",
            detail,
            progress_text,
            progress_current,
            progress_total,
            action_key,
            action_text,
        )
    if state.phase is SharedDataPhase.WAITING:
        detail = "当前任务继续使用创建时的配置，结束后会自动刷新。"
        return SharedDataDisplay(
            "等待当前任务完成后刷新实体数据",
            "等待任务",
            detail,
            state.status_role,
            "等待当前任务结束",
            detail,
            "",
            None,
            None,
            action_key,
            action_text,
        )
    if state.phase is SharedDataPhase.PREPARING:
        detail = f"正在更新{progress_text}" if progress_text else "正在修复旧版或缺失的结构化数据。"
        return SharedDataDisplay(
            "正在更新实体数据…",
            "更新中…",
            detail,
            state.status_role,
            "准备数据中",
            detail,
            progress_text,
            progress_current,
            progress_total,
            action_key,
            action_text,
        )
    if state.phase is SharedDataPhase.VERIFYING:
        detail = f"正在验证{progress_text}" if progress_text else "正在完整复检英雄与地图目录。"
        return SharedDataDisplay(
            "更新完成，正在验证实体数据…",
            "验证中…",
            detail,
            state.status_role,
            "准备数据中",
            detail,
            progress_text,
            progress_current,
            progress_total,
            action_key,
            action_text,
        )
    if state.phase is SharedDataPhase.READY:
        summary = state.summary
        detail = (
            f"已加载 {summary.champion_loaded} 个英雄和 {summary.map_loaded} 张地图。"
            if summary is not None
            else "英雄和地图目录已就绪。"
        )
        return SharedDataDisplay(
            "运行环境已就绪",
            "已就绪",
            detail,
            state.status_role,
            "创建任务",
            "",
            "",
            None,
            None,
            action_key,
            action_text,
        )
    if state.phase is SharedDataPhase.PARTIAL:
        detail = (
            f"{summary_text}；新任务已暂停。"
            if summary_text
            else f"{problem_text}；新任务已暂停。"
            if problem_text
            else "目录不完整，新任务已暂停。"
        )
        if problem_text and summary_text:
            detail = f"{detail} {problem_text}"
        return SharedDataDisplay(
            "部分实体数据未就绪",
            "部分就绪",
            detail,
            state.status_role,
            "创建任务",
            detail,
            "",
            None,
            None,
            action_key,
            action_text,
        )
    if state.phase is SharedDataPhase.CANCELLED:
        detail = "准备过程已取消；现有结果未被视为完整目录。"
        return SharedDataDisplay(
            "实体数据准备已取消",
            "已取消",
            detail,
            state.status_role,
            "创建任务",
            detail,
            "",
            None,
            None,
            action_key,
            action_text,
        )

    detail = problem_text or "共享数据未能形成可信目录，请重试更新。"
    return SharedDataDisplay(
        "实体数据准备失败",
        "准备失败",
        detail,
        state.status_role,
        "创建任务",
        detail,
        "",
        None,
        None,
        action_key,
        action_text,
    )


__all__ = ["SharedDataDisplay", "describe_shared_data_state"]
