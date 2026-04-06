"""GUI 页面布局 token 与通用样式辅助。"""

from __future__ import annotations

from PySide6.QtWidgets import QLayout, QWidget

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


def configure_transparent_scroll_page(
    scroll_area,
    *,
    page_object_name: str,
    view_object_name: str,
    view_stylesheet: str | None = None,
) -> QWidget:
    """为滚动页面配置统一的透明壳层。

    Args:
        scroll_area: 目标滚动页面实例。
        page_object_name: 页面对象名。
        view_object_name: 视图容器对象名。
        view_stylesheet: 可选的自定义视图样式；为空时默认使用透明背景。

    Returns:
        创建并挂载到滚动页面上的视图容器。
    """
    scroll_area.setObjectName(page_object_name)
    view = QWidget(scroll_area)
    view.setObjectName(view_object_name)
    resolved_view_stylesheet = view_stylesheet or f"QWidget#{view_object_name}{{background: transparent}}"
    view.setStyleSheet(resolved_view_stylesheet)
    scroll_area.setWidget(view)
    scroll_area.setWidgetResizable(True)
    scroll_area.setStyleSheet("QScrollArea {border: none; background: transparent;}")
    return view


__all__ = [
    "PAGE_CONTENT_MARGIN",
    "PAGE_CONTENT_MARGINS",
    "apply_page_content_margins",
    "configure_transparent_scroll_page",
]
