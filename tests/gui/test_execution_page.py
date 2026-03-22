"""测试执行中心日志面板同步逻辑。"""

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication

from lol_audio_unpack.gui.components.log_drawer import (
    LOG_PANEL_COLLAPSED_VISIBLE_HEIGHT,
    LOG_PANEL_HANDLE_SIZE,
    LOG_PANEL_MAX_HEIGHT,
    LOG_PANEL_MIN_HEIGHT,
    LOG_PANEL_MIN_TOP_GAP,
    LOG_PANEL_SIDE_MARGIN,
    LOG_PANEL_TOP_MARGIN,
    _build_log_panel_geometry,
    _build_log_panel_host_rect,
    _build_log_panel_toggle_rect,
    _resolve_log_panel_height,
)
from lol_audio_unpack.gui.view.execution_page import ExecutionPage


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
    """日志抽屉展开时应停靠底部，收起时应整体滑出内容区。"""
    host_rect = _build_log_panel_host_rect(QSize(1130, 800), navigation_width=48)

    collapsed = _build_log_panel_geometry(host_rect, expanded=False)
    expanded = _build_log_panel_geometry(host_rect, expanded=True)

    assert collapsed.height() == expanded.height()
    assert collapsed.left() == host_rect.left()
    assert expanded.left() == host_rect.left()
    assert collapsed.right() == host_rect.right()
    assert expanded.right() == host_rect.right()
    assert expanded.bottom() == host_rect.bottom()
    assert collapsed.top() == host_rect.bottom() + 1


def test_log_panel_geometry_respects_height_cap_for_large_window() -> None:
    """窗口较高时日志面板仍应受到最大高度限制。"""
    host_rect = _build_log_panel_host_rect(QSize(1440, 1600), navigation_width=64)

    expanded = _build_log_panel_geometry(host_rect, expanded=True)
    collapsed = _build_log_panel_geometry(host_rect, expanded=False)

    assert expanded.height() == collapsed.height()
    assert expanded.height() < host_rect.height() // 2
    assert expanded.top() > host_rect.top()
    assert collapsed.top() > host_rect.bottom()


def test_resolve_log_panel_height_clamps_default_and_dragged_height() -> None:
    """日志抽屉高度应同时遵守默认上限和拖拽后的窗口上限。"""
    host_rect = _build_log_panel_host_rect(QSize(1440, 1000), navigation_width=64)

    default_height = _resolve_log_panel_height(host_rect)
    dragged_height = _resolve_log_panel_height(host_rect, preferred_height=9999)
    expected_max_height = host_rect.height() - LOG_PANEL_TOP_MARGIN - LOG_PANEL_MIN_TOP_GAP

    assert LOG_PANEL_MIN_HEIGHT <= default_height <= LOG_PANEL_MAX_HEIGHT
    assert dragged_height == expected_max_height


def test_log_panel_toggle_rect_respects_collapsed_hover_only() -> None:
    """收起时按钮停靠右下角，悬停会上浮；展开态不再应用悬停动画。"""
    host_rect = _build_log_panel_host_rect(QSize(1130, 800), navigation_width=48)
    collapsed_panel = _build_log_panel_geometry(host_rect, expanded=False)
    expanded_panel = _build_log_panel_geometry(host_rect, expanded=True)

    collapsed_toggle = _build_log_panel_toggle_rect(
        host_rect,
        collapsed_panel,
        expanded=False,
        hovered=False,
    )
    hovered_toggle = _build_log_panel_toggle_rect(
        host_rect,
        collapsed_panel,
        expanded=False,
        hovered=True,
    )
    expanded_toggle = _build_log_panel_toggle_rect(
        host_rect,
        expanded_panel,
        expanded=True,
        hovered=False,
    )
    expanded_hovered_toggle = _build_log_panel_toggle_rect(
        host_rect,
        expanded_panel,
        expanded=True,
        hovered=True,
    )

    assert collapsed_toggle.width() == LOG_PANEL_HANDLE_SIZE
    assert collapsed_toggle.height() == LOG_PANEL_HANDLE_SIZE
    assert collapsed_toggle.right() == host_rect.right() - LOG_PANEL_SIDE_MARGIN
    assert collapsed_toggle.top() == collapsed_panel.top() - LOG_PANEL_COLLAPSED_VISIBLE_HEIGHT
    assert collapsed_toggle.bottom() > host_rect.bottom()
    assert hovered_toggle.top() < collapsed_toggle.top()
    assert expanded_toggle.top() == expanded_panel.top() - LOG_PANEL_HANDLE_SIZE // 2
    assert expanded_toggle.right() <= expanded_panel.right()
    assert expanded_hovered_toggle == expanded_toggle
