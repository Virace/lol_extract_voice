"""主窗口壳层同步 helper。"""

from __future__ import annotations

from collections.abc import Callable

from loguru import logger
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import NavigationItemPosition

from lol_audio_unpack.gui.common import apply_smooth_scroll_enabled
from lol_audio_unpack.gui.controllers.contracts import RuntimeLoggingConfig
from lol_audio_unpack.utils.logging import setup_logging


def apply_task_queue_busy_state(
    *,
    busy: bool,
    setting_page,
    navigation_interface,
    shared_data_controller,
) -> None:
    """同步执行队列忙碌状态到主窗口壳层。"""
    setting_page.set_runtime_config_locked(busy)
    refresh_widget = navigation_interface.widget("refreshSharedData")
    if refresh_widget is not None:
        refresh_widget.setEnabled(not busy)
    if shared_data_controller is not None:
        shared_data_controller.set_queue_busy(busy)


def apply_runtime_logging(
    *,
    payload: RuntimeLoggingConfig,
    execution_page,
) -> None:
    """重挂运行时日志输出并刷新 GUI sink。"""
    setup_logging(
        dev_mode=True,
        log_level=payload.console_log_level,
        file_log_level=payload.file_log_level,
        log_file_path=payload.log_dir,
        show_function_info=True,
    )
    execution_page.attach_runtime_log_sink(payload.console_log_level)
    logger.debug(f"日志系统已重定向到输出目录: {payload.log_dir}")


def sync_existing_runtime_logging(
    *,
    console_log_level: str,
    execution_page,
) -> None:
    """在不重建文件 handler 的前提下重挂 GUI 日志 sink。"""
    execution_page.attach_runtime_log_sink(console_log_level)


def apply_smooth_scroll_settings(  # noqa: PLR0913
    *,
    setting_page,
    home_page,
    about_page,
    execution_page,
    overview_page,
    log_output_widget,
    page_enabled: bool,
    widget_enabled: bool,
) -> None:
    """统一应用 GUI 的平滑滚动设置。"""
    apply_smooth_scroll_enabled(setting_page, page_enabled)
    apply_smooth_scroll_enabled(home_page, page_enabled)
    apply_smooth_scroll_enabled(about_page, page_enabled)
    execution_page.set_smooth_scroll_enabled(
        page_enabled=page_enabled,
        widget_enabled=widget_enabled,
    )
    overview_page.set_smooth_scroll_enabled(widget_enabled)
    if log_output_widget is not None:
        apply_smooth_scroll_enabled(log_output_widget, widget_enabled)


def forward_selection_sync_feedback(
    *,
    payload,
    execution_page,
    feedback_parent,
    show_feedback: Callable[..., None],
) -> None:
    """处理总览页向执行中心同步后的全局反馈。"""
    summary = execution_page.set_selected_entities(payload, feedback_parent=feedback_parent)
    if summary is None:
        return
    show_feedback(
        title="已同步到执行中心",
        content=summary,
        parent=feedback_parent,
        level="success",
    )


def register_navigation_items(window, shared_data_controller) -> None:
    """注册主窗口导航项。"""
    window.addSubInterface(window.homeInterface, FIF.HOME, "主页")
    window.addSubInterface(window.executionInterface, FIF.DOWNLOAD, "执行中心")
    window.addSubInterface(window.overviewInterface, FIF.DOCUMENT, "实体总览")

    window.navigationInterface.addSeparator()
    window.navigationInterface.addItem(
        routeKey="refreshSharedData",
        icon=FIF.SYNC,
        text="刷新数据",
        onClick=shared_data_controller.refresh_shared_output_state,
        selectable=False,
    )
    window.navigationInterface.addItem(
        routeKey="themeSwitcher",
        icon=FIF.PALETTE,
        text="主题切换",
        onClick=window.toggleTheme,
        selectable=False,
        position=NavigationItemPosition.BOTTOM,
    )
    window.addSubInterface(
        window.settingInterface,
        FIF.SETTING,
        "全局设置",
        position=NavigationItemPosition.BOTTOM,
    )
    window.addSubInterface(
        window.aboutInterface,
        FIF.INFO,
        "关于",
        position=NavigationItemPosition.BOTTOM,
    )
    window.navigationInterface.setExpandWidth(180)


def bind_shared_data_controller_signals(  # noqa: PLR0913
    controller,
    *,
    home_page,
    execution_page,
    overview_page,
    feedback_parent,
    show_feedback: Callable[..., None],
    on_reconfigure_runtime_logging: Callable[[RuntimeLoggingConfig], None],
) -> None:
    """把共享数据控制器的信号接到窗口壳层。"""
    controller.loading_state_changed.connect(
        lambda state: home_page.set_loading_state(state.message, active=state.active)
    )
    controller.shared_data_cleared.connect(execution_page.clear_entity_data)
    controller.shared_data_cleared.connect(overview_page.clear_data)
    controller.app_context_changed.connect(overview_page.set_app_context)
    controller.entity_data_replaced.connect(
        lambda payload: execution_page.set_entity_data(payload.entity_type, list(payload.rows))
    )
    controller.entity_data_replaced.connect(
        lambda payload: overview_page.set_entity_data(payload.entity_type, list(payload.rows))
    )
    controller.entity_rows_updated.connect(
        lambda payload: execution_page.update_entity_rows(payload.entity_type, list(payload.rows))
    )
    controller.entity_rows_updated.connect(
        lambda payload: overview_page.update_entity_rows(payload.entity_type, list(payload.rows))
    )
    controller.notice_requested.connect(
        lambda notice: show_feedback(
            title=notice.title,
            content=notice.content,
            parent=feedback_parent,
            level=notice.level,
        )
    )
    controller.reconfigure_runtime_logging_requested.connect(on_reconfigure_runtime_logging)
