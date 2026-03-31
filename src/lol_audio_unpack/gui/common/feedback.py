"""GUI 全局通知辅助逻辑。"""

from __future__ import annotations

from qfluentwidgets import InfoBar, InfoBarPosition


def calculate_feedback_duration(*, title: str, content: str, level: str) -> int:
    """根据通知级别和文本长度计算合适的停留时长。"""
    normalized_level = level.lower()
    if normalized_level == "error":
        return -1

    base_duration = {
        "success": 3200,
        "info": 3800,
        "warning": 5600,
    }.get(normalized_level, 4000)

    text = f"{title} {content}".strip()
    weighted_length = len(text) + content.count("\n") * 18
    extra_duration = max(weighted_length - 24, 0) * 28
    if normalized_level in {"warning", "error"}:
        extra_duration += 600

    return min(base_duration + extra_duration, 15000)


def show_feedback_infobar(
    *,
    parent,
    title: str,
    content: str,
    level: str,
    position=InfoBarPosition.TOP,
) -> None:
    """按统一策略显示全局 InfoBar。"""
    normalized_level = level.lower()
    factory = {
        "success": InfoBar.success,
        "info": InfoBar.info,
        "warning": InfoBar.warning,
        "error": InfoBar.error,
    }.get(normalized_level, InfoBar.info)

    factory(
        title=title,
        content=content,
        isClosable=True,
        position=position,
        duration=calculate_feedback_duration(title=title, content=content, level=normalized_level),
        parent=parent,
    )
