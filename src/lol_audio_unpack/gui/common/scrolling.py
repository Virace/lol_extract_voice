"""GUI 滚动行为配置辅助函数。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from qfluentwidgets.common.smooth_scroll import SmoothMode

DEFAULT_SCROLL_ANIMATION_DURATION = 500


def apply_smooth_scroll_enabled(widget, enabled: bool) -> None:
    """根据配置启用或关闭控件的平滑滚动。

    Args:
        widget: 需要应用滚动配置的 Qt / QFluentWidgets 控件。
        enabled: 是否启用平滑滚动。
    """

    mode = SmoothMode.LINEAR if enabled else SmoothMode.NO_SMOOTH
    duration = DEFAULT_SCROLL_ANIMATION_DURATION if enabled else 0

    # ListWidget / TableWidget / PlainTextEdit 等常见代理命名
    delegate = getattr(widget, "scrollDelegate", None) or getattr(widget, "scrollDelagate", None)
    if delegate is not None:
        if hasattr(delegate, "verticalSmoothScroll"):
            delegate.verticalSmoothScroll.setSmoothMode(mode)
        if hasattr(delegate, "horizonSmoothScroll"):
            delegate.horizonSmoothScroll.setSmoothMode(mode)

    # SmoothScrollArea 使用 delegate + animated scroll bar
    smooth_delegate = getattr(widget, "delegate", None)
    if smooth_delegate is not None:
        if hasattr(smooth_delegate, "verticalSmoothScroll"):
            smooth_delegate.verticalSmoothScroll.setSmoothMode(mode)
        if hasattr(smooth_delegate, "horizonSmoothScroll"):
            smooth_delegate.horizonSmoothScroll.setSmoothMode(mode)
        if hasattr(smooth_delegate, "vScrollBar") and hasattr(smooth_delegate.vScrollBar, "setScrollAnimation"):
            smooth_delegate.vScrollBar.setScrollAnimation(duration)
        if hasattr(smooth_delegate, "hScrollBar") and hasattr(smooth_delegate.hScrollBar, "setScrollAnimation"):
            smooth_delegate.hScrollBar.setScrollAnimation(duration)

    if hasattr(widget, "setScrollAnimation"):
        widget.setScrollAnimation(Qt.Vertical, duration)
        widget.setScrollAnimation(Qt.Horizontal, duration)
