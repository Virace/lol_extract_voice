"""GUI 页面布局 token 与通用样式辅助。"""

from __future__ import annotations

from PySide6.QtWidgets import QLayout

PAGE_CONTENT_MARGIN = 24
PAGE_CONTENT_MARGINS = (
    PAGE_CONTENT_MARGIN,
    PAGE_CONTENT_MARGIN,
    PAGE_CONTENT_MARGIN,
    PAGE_CONTENT_MARGIN,
)


def apply_page_content_margins(layout: QLayout) -> None:
    """对顶层页面布局应用统一页边距 token。

    Args:
        layout: 需要写入页边距的页面根布局。
    """
    layout.setContentsMargins(*PAGE_CONTENT_MARGINS)


__all__ = [
    "PAGE_CONTENT_MARGIN",
    "PAGE_CONTENT_MARGINS",
    "apply_page_content_margins",
]
