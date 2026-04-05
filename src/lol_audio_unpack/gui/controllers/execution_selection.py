"""执行中心的选择同步控制器。"""

from __future__ import annotations

from dataclasses import dataclass


def _build_target_summary(champion_ids: tuple[str, ...], map_ids: tuple[str, ...]) -> str:
    """构造当前目标范围摘要。"""
    if not champion_ids and not map_ids:
        return "全部英雄+地图"
    return f"目标：英雄 {len(champion_ids)} 个，地图 {len(map_ids)} 个"


def _merge_unique_ids(base_ids: tuple[str, ...], incoming_ids: tuple[str, ...]) -> tuple[str, ...]:
    """合并两组 ID，并保持原有顺序去重。"""
    merged = list(base_ids)
    seen = set(base_ids)
    for entity_id in incoming_ids:
        if entity_id not in seen:
            seen.add(entity_id)
            merged.append(entity_id)
    return tuple(merged)


@dataclass(slots=True, frozen=True)
class ExecutionSelectionUpdate:
    """描述一次执行中心目标同步后的结果。"""

    champion_ids: tuple[str, ...]
    map_ids: tuple[str, ...]
    source: str
    summary: str


class ExecutionSelectionController:
    """负责执行中心目标选择同步与冲突收敛。"""

    def has_conflict(
        self,
        *,
        current_champion_ids: tuple[str, ...],
        current_map_ids: tuple[str, ...],
        incoming_champion_ids: tuple[str, ...],
        incoming_map_ids: tuple[str, ...],
    ) -> bool:
        """判断当前输入和新选择之间是否存在冲突。"""
        return bool(current_champion_ids or current_map_ids) and (
            current_champion_ids != incoming_champion_ids or current_map_ids != incoming_map_ids
        )

    def build_conflict_dialog_content(
        self,
        *,
        current_champion_ids: tuple[str, ...],
        current_map_ids: tuple[str, ...],
        incoming_champion_ids: tuple[str, ...],
        incoming_map_ids: tuple[str, ...],
    ) -> str:
        """构造目标同步冲突提示文本。"""
        return (
            "执行中心里已经填写了目标。\n\n"
            f"当前任务：{_build_target_summary(current_champion_ids, current_map_ids)}\n"
            f"新选择：{_build_target_summary(incoming_champion_ids, incoming_map_ids)}\n\n"
            "你可以选择覆盖、合并，或取消这次同步。"
        )

    def resolve_selection_update(  # noqa: PLR0913
        self,
        *,
        current_champion_ids: tuple[str, ...],
        current_map_ids: tuple[str, ...],
        incoming_champion_ids: tuple[str, ...],
        incoming_map_ids: tuple[str, ...],
        source: str,
        summary: str,
        resolution: str | None,
    ) -> ExecutionSelectionUpdate | None:
        """根据冲突处理策略收敛最终要应用的选择结果。"""
        champion_ids = incoming_champion_ids
        map_ids = incoming_map_ids

        if self.has_conflict(
            current_champion_ids=current_champion_ids,
            current_map_ids=current_map_ids,
            incoming_champion_ids=incoming_champion_ids,
            incoming_map_ids=incoming_map_ids,
        ):
            if resolution == "cancel":
                return None
            if resolution == "merge":
                champion_ids = _merge_unique_ids(current_champion_ids, incoming_champion_ids)
                map_ids = _merge_unique_ids(current_map_ids, incoming_map_ids)
                summary = (
                    f"已合并到当前任务：{len(champion_ids)} 个英雄、{len(map_ids)} 张地图。"
                    "请前往执行中心继续创建任务。"
                )
            else:
                summary = (
                    f"已同步 {len(champion_ids)} 个英雄、{len(map_ids)} 张地图，"
                    "请前往执行中心继续创建任务。"
                )
        elif summary == "未提供摘要":
            summary = (
                f"已同步 {len(champion_ids)} 个英雄、{len(map_ids)} 张地图，"
                "请前往执行中心继续创建任务。"
            )

        return ExecutionSelectionUpdate(
            champion_ids=champion_ids,
            map_ids=map_ids,
            source=source,
            summary=summary,
        )
