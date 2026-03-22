"""测试执行中心日志面板同步逻辑。"""

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication

from lol_audio_unpack.gui.view.execution_page import ExecutionPage
from lol_audio_unpack.gui.window import (
    LOG_PANEL_BOTTOM_MARGIN,
    LOG_PANEL_COLLAPSED_HEIGHT,
    LOG_PANEL_SIDE_MARGIN,
    _build_log_panel_geometry,
    _build_log_panel_host_rect,
)


def test_execution_page_emits_full_log_text_when_appending() -> None:
    """执行中心追加日志后应同步发出完整文本，且不再保留页内日志卡片。"""
    app = QApplication.instance() or QApplication([])
    page = ExecutionPage()
    received: list[str] = []
    page.log_text_changed.connect(received.append)

    page._append_log_line("[测试] 触发全局日志同步")
    app.processEvents()

    assert received
    assert received[-1].endswith("[测试] 触发全局日志同步")
    assert page.current_log_text() == received[-1]
    assert not hasattr(page, "log_card")


def test_log_panel_geometry_stays_inside_content_area() -> None:
    """全局日志面板应固定停靠在页面内容区底部并保留左右边距。"""
    host_rect = _build_log_panel_host_rect(QSize(1130, 800), navigation_width=48)

    collapsed = _build_log_panel_geometry(host_rect, expanded=False)
    expanded = _build_log_panel_geometry(host_rect, expanded=True)

    assert collapsed.height() == LOG_PANEL_COLLAPSED_HEIGHT
    assert expanded.height() > collapsed.height()
    assert collapsed.left() == host_rect.left() + LOG_PANEL_SIDE_MARGIN
    assert expanded.left() == host_rect.left() + LOG_PANEL_SIDE_MARGIN
    assert collapsed.right() == host_rect.right() - LOG_PANEL_SIDE_MARGIN
    assert expanded.right() == host_rect.right() - LOG_PANEL_SIDE_MARGIN
    assert collapsed.bottom() == host_rect.bottom() - LOG_PANEL_BOTTOM_MARGIN
    assert expanded.bottom() == host_rect.bottom() - LOG_PANEL_BOTTOM_MARGIN


def test_log_panel_geometry_respects_height_cap_for_large_window() -> None:
    """窗口较高时日志面板仍应受到最大高度限制。"""
    host_rect = _build_log_panel_host_rect(QSize(1440, 1600), navigation_width=64)

    expanded = _build_log_panel_geometry(host_rect, expanded=True)
    collapsed = _build_log_panel_geometry(host_rect, expanded=False)

    assert expanded.height() > collapsed.height()
    assert expanded.height() < host_rect.height() // 2
    assert expanded.top() > host_rect.top()
