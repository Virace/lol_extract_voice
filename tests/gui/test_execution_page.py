"""测试执行中心日志面板同步逻辑。"""

from loguru import logger
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QApplication, QWidget

from lol_audio_unpack.gui.common import (
    clear_buffered_log_lines,
    install_startup_log_buffer,
    remove_startup_log_buffer,
)
from lol_audio_unpack.gui.common.loguru_palette import ANSI_FIXED_HEX_BY_SGR
from lol_audio_unpack.gui.components.log_drawer import (
    LOG_PANEL_COLLAPSED_VISIBLE_HEIGHT,
    LOG_PANEL_HANDLE_SIZE,
    LOG_PANEL_MAX_HEIGHT,
    LOG_PANEL_MIN_HEIGHT,
    LOG_PANEL_MIN_TOP_GAP,
    LOG_PANEL_SIDE_MARGIN,
    LOG_PANEL_TOP_MARGIN,
    GlobalLogDrawer,
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
    page.deleteLater()
    app.processEvents()


def test_execution_page_preloads_buffered_startup_logs() -> None:
    """执行中心初始化时应带上启动期已缓冲的日志。"""
    app = QApplication.instance() or QApplication([])
    clear_buffered_log_lines()
    install_startup_log_buffer()

    try:
        logger.info("GUI 启动前置日志")
        page = ExecutionPage()
        app.processEvents()

        assert "GUI 启动前置日志" in page.current_log_text()
        page.deleteLater()
        app.processEvents()
    finally:
        remove_startup_log_buffer()
        clear_buffered_log_lines()


def test_execution_page_attaches_real_runtime_logs_to_buffer() -> None:
    """执行中心应能接收真实 loguru 输出并落入累计日志文本。"""
    app = QApplication.instance() or QApplication([])
    page = ExecutionPage()
    batches: list[tuple[str, ...]] = []
    page.log_lines_appended.connect(batches.append)
    page.attach_runtime_log_sink()

    logger.info("GUI 日志桥接测试")
    app.processEvents()

    assert batches
    assert any("GUI 日志桥接测试" in line for batch in batches for line in batch)
    assert "GUI 日志桥接测试" in page.current_log_text()
    page.deleteLater()
    app.processEvents()


def test_execution_page_batches_runtime_logs_before_render() -> None:
    """高频运行时日志应先合批，再增量推送给主窗口抽屉。"""
    app = QApplication.instance() or QApplication([])
    page = ExecutionPage()
    batches: list[tuple[str, ...]] = []
    full_text_updates: list[str] = []
    page.log_lines_appended.connect(batches.append)
    page.log_text_changed.connect(full_text_updates.append)

    page._queue_runtime_log_line("[测试] 第一条运行时日志")
    page._queue_runtime_log_line("[测试] 第二条运行时日志")
    app.processEvents()

    assert batches == [
        ("[测试] 第一条运行时日志", "[测试] 第二条运行时日志"),
    ]
    assert not full_text_updates
    assert page.current_log_text().endswith("[测试] 第二条运行时日志")
    page.deleteLater()
    app.processEvents()


def test_global_log_drawer_keeps_appending_while_collapsed() -> None:
    """日志抽屉在隐藏状态下也应持续追加文本并保持滚动到底部。"""
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.resize(1130, 800)
    drawer = GlobalLogDrawer(host)
    drawer.sync_host_rect(_build_log_panel_host_rect(host.size(), navigation_width=48), animate=False)
    drawer.set_expanded(False, animate=False)

    drawer.append_log_lines(("[测试] 抽屉隐藏中持续渲染", "[测试] 多日志批量追加完成"))
    app.processEvents()

    output = drawer.output_widget.toPlainText()
    scrollbar = drawer.output_widget.verticalScrollBar()
    assert "[测试] 抽屉隐藏中持续渲染" in output
    assert output.endswith("[测试] 多日志批量追加完成")
    assert scrollbar.value() == scrollbar.maximum()
    host.deleteLater()
    app.processEvents()


def test_global_log_drawer_follow_scroll_switch_defaults_to_enabled() -> None:
    """日志抽屉默认应保持跟随最新日志滚动。"""
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.resize(1130, 800)
    drawer = GlobalLogDrawer(host)
    app.processEvents()

    assert drawer._follow_scroll_switch.isChecked()
    assert drawer._follow_output_scroll is True

    host.deleteLater()
    app.processEvents()


def test_global_log_drawer_can_disable_follow_scroll() -> None:
    """关闭保持滚动后，新日志不应强制把滚动条拖回底部。"""
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.resize(1130, 800)
    drawer = GlobalLogDrawer(host)
    drawer.set_log_text("\n".join(f"[测试] 初始日志 {i}" for i in range(600)))
    app.processEvents()

    scrollbar = drawer.output_widget.verticalScrollBar()
    assert scrollbar.maximum() > 0

    drawer.set_follow_scroll_enabled(False)
    scrollbar.setValue(0)
    drawer.append_log_lines(("[测试] 新增日志 A", "[测试] 新增日志 B"))
    app.processEvents()

    assert drawer._follow_scroll_switch.isChecked() is False
    assert scrollbar.value() == 0

    host.deleteLater()
    app.processEvents()


def test_global_log_drawer_backdrop_respects_auto_collapse_setting() -> None:
    """蒙版应在展开时出现，并根据设置决定是否拦截外部点击。"""
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.resize(1130, 800)
    host.show()
    drawer = GlobalLogDrawer(host)
    drawer.sync_host_rect(_build_log_panel_host_rect(host.size(), navigation_width=48), animate=False)
    drawer.set_expanded(True, animate=False)
    app.processEvents()

    assert drawer._backdrop.isVisible()
    assert drawer._backdrop.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) is False

    drawer.set_auto_collapse_enabled(False)
    app.processEvents()

    assert drawer._backdrop.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    host.deleteLater()
    app.processEvents()


def test_global_log_drawer_backdrop_click_collapses_panel() -> None:
    """启用自动收起时，点击蒙版应收起日志抽屉。"""
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.resize(1130, 800)
    host.show()
    drawer = GlobalLogDrawer(host)
    drawer.sync_host_rect(_build_log_panel_host_rect(host.size(), navigation_width=48), animate=False)
    drawer.set_auto_collapse_enabled(True)
    drawer.set_expanded(True, animate=False)
    app.processEvents()

    drawer._backdrop.clicked.emit()
    app.processEvents()

    assert drawer._expanded is False
    assert drawer._backdrop.isVisible() is False

    host.deleteLater()
    app.processEvents()


def test_global_log_drawer_stylesheet_contains_theme_text_color() -> None:
    """日志抽屉正文样式应显式声明前景色。"""
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.resize(1130, 800)
    drawer = GlobalLogDrawer(host)
    app.processEvents()

    assert "color:" in drawer.output_widget.styleSheet()

    host.deleteLater()
    app.processEvents()


def test_log_drawer_highlighter_uses_level_color_for_message() -> None:
    """级别颜色应同时作用于级别字段和消息正文，INFO 保持正文默认色。"""
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.resize(1130, 800)
    drawer = GlobalLogDrawer(host)
    app.processEvents()

    base_color = drawer._highlighter._base_format.foreground().color()
    info_level_color = drawer._highlighter._level_formats["INFO"].foreground().color()
    info_message_color = drawer._highlighter._message_formats["INFO"].foreground().color()
    error_level_color = drawer._highlighter._level_formats["ERROR"].foreground().color()
    error_message_color = drawer._highlighter._message_formats["ERROR"].foreground().color()
    debug_level_color = drawer._highlighter._level_formats["DEBUG"].foreground().color()
    warning_level_color = drawer._highlighter._message_formats["WARNING"].foreground().color()
    critical_background = drawer._highlighter._message_formats["CRITICAL"].background().color()

    assert info_level_color == info_message_color
    assert info_message_color == base_color
    assert error_level_color == error_message_color
    assert error_message_color != info_message_color
    assert debug_level_color.name() == ANSI_FIXED_HEX_BY_SGR[34].lower()
    assert warning_level_color.name() == ANSI_FIXED_HEX_BY_SGR[33].lower()
    assert critical_background.name() == ANSI_FIXED_HEX_BY_SGR[41].lower()

    host.deleteLater()
    app.processEvents()


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
