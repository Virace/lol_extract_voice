"""应用主窗口与页面装配逻辑。"""

from __future__ import annotations

import sys
from pathlib import Path
from time import perf_counter

from loguru import logger
from PySide6.QtCore import QEvent, QPoint, QRect, QSize, QThreadPool, QTimer
from PySide6.QtGui import QCloseEvent, QIcon, QResizeEvent, QShowEvent
from PySide6.QtWidgets import QApplication, QMessageBox, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import (
    FluentWindow,
    InfoBar,
    InfoBarPosition,
    NavigationItemPosition,
    SplashScreen,
    Theme,
    qconfig,
    setTheme,
    setThemeColor,
)

from lol_audio_unpack import __version__
from lol_audio_unpack.app.context import create_app_context
from lol_audio_unpack.app.facade import LolAudioUnpackApp
from lol_audio_unpack.app.types import OperationOptions
from lol_audio_unpack.config import SettingKey
from lol_audio_unpack.gui.common import (
    apply_smooth_scroll_enabled,
    get_app_context_block_reason,
    show_feedback_infobar,
)
from lol_audio_unpack.gui.common.packaged_remote_mode_policy import normalize_app_context_settings
from lol_audio_unpack.gui.components.global_progress_strip import GlobalProgressStripHost
from lol_audio_unpack.gui.components.log_drawer import (
    GlobalLogDrawer,
)
from lol_audio_unpack.gui.controllers import (
    DevConsoleController,
    LogDrawerController,
    SharedDataController,
)
from lol_audio_unpack.gui.controllers.contracts import RuntimeLoggingConfig
from lol_audio_unpack.gui.controllers.shared_data import (
    build_shared_entity_reader_signature,
    build_shared_entity_scan_signature,
)
from lol_audio_unpack.gui.controllers.window_shell import (
    apply_runtime_logging,
    apply_smooth_scroll_settings,
    apply_task_queue_busy_state,
    bind_shared_data_controller_signals,
    confirm_force_close_running_tasks,
    force_quit_application,
    forward_selection_sync_feedback,
    register_navigation_items,
    sync_existing_runtime_logging,
)
from lol_audio_unpack.gui.resources import assets
from lol_audio_unpack.gui.service.data_loader import EntityDataLoader
from lol_audio_unpack.gui.service.worker import DataLoadWorker
from lol_audio_unpack.gui.view.about_page import AboutPage, get_about_page_minimum_shell_size
from lol_audio_unpack.gui.view.execution_page import ExecutionPage
from lol_audio_unpack.gui.view.home_page import HomePage
from lol_audio_unpack.gui.view.overview_page import OverviewPage
from lol_audio_unpack.gui.view.setting_page import SettingPage
from lol_audio_unpack.gui.workers import TaskWorker
from lol_audio_unpack.manager.data_reader import DataReader
from lol_audio_unpack.utils.common import Singleton
from lol_audio_unpack.utils.logging import setup_logging

NAV_EXPANDED_WIDTH_THRESHOLD = 100


def _log_window_stage(stage: str, startup_begin: float, previous_mark: float) -> float:
    """记录主窗口初始化阶段耗时。"""
    current_mark = perf_counter()
    logger.trace(
        "主窗口阶段 | {} | 本段 {:.3f}s | 累计 {:.3f}s",
        stage,
        current_mark - previous_mark,
        current_mark - startup_begin,
    )
    return current_mark


def _prepare_shared_entity_data(shared_settings: dict[str, str | bool]) -> None:
    """为实体列表准备后端共享数据。"""
    prepare_settings = dict(shared_settings)
    prepare_settings[SettingKey.WITH_BP_VO] = True
    prepare_settings = normalize_app_context_settings(prepare_settings)
    app_context = create_app_context(settings=prepare_settings)
    app = LolAudioUnpackApp(app_context)
    app.update(OperationOptions(), target="all")


def _reset_data_reader_singleton() -> None:
    """重置 ``DataReader`` 单例，确保后续读取使用新的上下文。"""
    if DataReader in Singleton._instances:
        logger.debug("检测到共享实体数据读取上下文已变化，重置 DataReader 单例缓存")
        del Singleton._instances[DataReader]


class MainWindow(FluentWindow):
    """应用主窗口。"""

    def __init__(self):
        startup_begin = perf_counter()
        previous_mark = startup_begin
        self._log_drawer_controller = LogDrawerController()
        super().__init__()
        previous_mark = _log_window_stage("FluentWindow 基类初始化", startup_begin, previous_mark)
        self._progress_strip_host = GlobalProgressStripHost(self)
        self._content_shell = QWidget(self)
        self._content_shell_layout = QVBoxLayout(self._content_shell)
        self._content_shell_layout.setContentsMargins(0, 0, 0, 0)
        self._content_shell_layout.setSpacing(0)
        self.widgetLayout.setContentsMargins(0, 48, 0, 0)
        self.widgetLayout.removeWidget(self.stackedWidget)
        self._content_shell_layout.addWidget(self.stackedWidget, 1)
        self._content_shell_layout.addWidget(self._progress_strip_host, 0)
        self.widgetLayout.addWidget(self._content_shell)
        self.titleBar.raise_()
        previous_mark = _log_window_stage("主内容壳层初始化完成", startup_begin, previous_mark)

        # apply specific real-time listeners for theme tracking
        qconfig.themeChanged.connect(setTheme)
        qconfig.themeColorChanged.connect(setThemeColor)
        self._theme_material_listener = lambda _theme: self._try_enable_window_material()
        qconfig.themeChanged.connect(self._theme_material_listener)
        previous_mark = _log_window_stage("主题变更信号连接完成", startup_begin, previous_mark)

        self._shared_data_controller: SharedDataController | None = None
        self._window_material_bootstrapped = False
        self._last_window_material_logged_state: bool | None = None
        self._dev_console_controller: DevConsoleController | None = None
        self._app_event_filter_host = QApplication.instance()
        self._app_event_filter_installed = False
        self.destroyed.connect(lambda *_args: self._unregister_app_event_filter())

        self._initWindow()
        previous_mark = _log_window_stage("窗口属性初始化完成", startup_begin, previous_mark)

        # create splash screen after the shell has a real icon and size
        self.splashScreen = SplashScreen(self.windowIcon(), self)
        self.splashScreen.setIconSize(QSize(106, 106))
        self.splashScreen.raise_()
        previous_mark = _log_window_stage("SplashScreen 初始化完成", startup_begin, previous_mark)

        self.show()
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        previous_mark = _log_window_stage("主窗口预显示完成", startup_begin, previous_mark)

        previous_mark = self._bootstrap_after_show(startup_begin, previous_mark)

        self.splashScreen.finish()
        _log_window_stage("SplashScreen 结束", startup_begin, previous_mark)

    def _bootstrap_after_show(self, startup_begin: float, previous_mark: float) -> float:
        """在主窗口显示后继续构建子页面与启动链。"""
        # create sub interface — SettingPage first so cfg is ready
        self.settingInterface = SettingPage(self)
        previous_mark = _log_window_stage("SettingPage 初始化完成", startup_begin, previous_mark)
        cfg = self.settingInterface.config

        self.homeInterface = HomePage(cfg, self)
        previous_mark = _log_window_stage("HomePage 初始化完成", startup_begin, previous_mark)
        self.executionInterface = ExecutionPage(self)
        previous_mark = _log_window_stage("ExecutionPage 初始化完成", startup_begin, previous_mark)
        self.overviewInterface = OverviewPage(self)
        previous_mark = _log_window_stage("OverviewPage 初始化完成", startup_begin, previous_mark)
        self.aboutInterface = AboutPage(self)
        previous_mark = _log_window_stage("AboutPage 初始化完成", startup_begin, previous_mark)
        self._shared_data_controller = SharedDataController(
            get_config=lambda: self.settingInterface.config,
            has_incomplete_tasks=self.executionInterface.has_incomplete_tasks,
            create_app_context_fn=create_app_context,
            data_load_worker_cls=DataLoadWorker,
            task_worker_cls=TaskWorker,
            entity_data_loader_cls=EntityDataLoader,
            start_worker_fn=lambda worker: QThreadPool.globalInstance().start(worker),
            prepare_shared_entity_data_fn=_prepare_shared_entity_data,
            reset_data_reader_singleton_fn=_reset_data_reader_singleton,
            app_context_block_reason_fn=get_app_context_block_reason,
            parent=self,
        )

        register_navigation_items(self, self._shared_data_controller)
        previous_mark = _log_window_stage("导航初始化完成", startup_begin, previous_mark)
        self._log_drawer_controller.ensure_drawer(
            host=self,
            current_log_text=self.executionInterface.current_log_text(),
            window_size=self.size(),
            navigation_width=self.navigationInterface.width(),
            on_dev_console_requested=self._show_dev_console,
        )
        previous_mark = _log_window_stage("全局日志面板初始化完成", startup_begin, previous_mark)

        # 连接设置页面和首页
        self._connect_pages()
        previous_mark = _log_window_stage("页面连接与首轮数据加载触发完成", startup_begin, previous_mark)
        return previous_mark

    def _initWindow(self):
        """设置主窗口尺寸、标题与基础事件过滤器。"""
        self.resize(1130, 800)
        about_min_size = get_about_page_minimum_shell_size()
        self.setMinimumWidth(max(860, about_min_size.width()))
        self.setMinimumHeight(about_min_size.height())
        self.setWindowIcon(assets.app.window_icon())
        self.setWindowTitle(f"Lol Audio Unpack  {__version__}")

        # Calculate screen center
        desktop = QApplication.primaryScreen().availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(int(w / 2 - self.width() / 2), int(h / 2 - self.height() / 2))

        # Install event filter to catch clicks outside the navigation bar
        if self._app_event_filter_host is not None:
            self._app_event_filter_host.installEventFilter(self)
            self._app_event_filter_installed = True

    def _unregister_app_event_filter(self) -> None:
        """从 ``QApplication`` 解除当前主窗口注册的全局 event filter。"""
        if not self._app_event_filter_installed or self._app_event_filter_host is None:
            return
        try:
            self._app_event_filter_host.removeEventFilter(self)
        except RuntimeError:
            return
        self._app_event_filter_installed = False

    def _disconnect_theme_material_listener(self) -> None:
        """断开当前窗口注册的主题材质刷新监听。"""
        listener = getattr(self, "_theme_material_listener", None)
        if listener is None:
            return
        try:
            qconfig.themeChanged.disconnect(listener)
        except (RuntimeError, TypeError):
            pass
        self._theme_material_listener = None

    def _try_enable_window_material(self) -> None:
        """在支持的平台上启用 Windows 原生 Mica Alt 材质。"""
        if sys.platform != "win32" or not self.isVisible():
            return

        is_dark_mode = qconfig.theme == Theme.DARK
        try:
            self.windowEffect.setMicaEffect(
                self.winId(),
                isDarkMode=is_dark_mode,
                isAlt=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"启用 Mica Alt 材质失败: {exc}")
            return

        if self._last_window_material_logged_state != is_dark_mode:
            logger.trace("主窗口已应用 Mica Alt 材质效果")
            self._last_window_material_logged_state = is_dark_mode

    def _schedule_window_material_refresh(self, *, delay_ms: int = 0) -> None:
        """安排下一轮窗口材质刷新。"""
        if sys.platform != "win32":
            return
        QTimer.singleShot(delay_ms, self._try_enable_window_material)

    def showEvent(self, event: QShowEvent) -> None:
        """在窗口首次显示后补刷 Mica，避免首帧材质未生效。"""
        super().showEvent(event)
        self._schedule_window_material_refresh()
        if not self._window_material_bootstrapped:
            self._window_material_bootstrapped = True
            self._schedule_window_material_refresh(delay_ms=80)
            self._schedule_window_material_refresh(delay_ms=180)

    def event(self, event):
        """在窗口激活状态变化后重刷 Mica，修正首轮焦点切换才生效的问题。"""
        if event.type() == QEvent.Type.DeferredDelete:
            self._disconnect_theme_material_listener()
            self._unregister_app_event_filter()
        if event.type() in {
            QEvent.Type.WindowActivate,
            QEvent.Type.WindowDeactivate,
            QEvent.Type.WinIdChange,
        }:
            self._schedule_window_material_refresh()
        return super().event(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        """关闭窗口前解除 QApplication 级事件过滤器。"""
        if (
            getattr(self, "executionInterface", None) is not None
            and self.executionInterface.is_task_running()
            and not confirm_force_close_running_tasks(parent=self)
        ):
            event.ignore()
            return
        should_force_quit = self._has_active_background_work()
        if should_force_quit:
            self._shutdown_background_work()
        self._disconnect_theme_material_listener()
        self._unregister_app_event_filter()
        super().closeEvent(event)
        if should_force_quit:
            force_quit_application(app=QApplication.instance())

    def _init_dev_console(self) -> None:
        """按需初始化隐藏开发控制台并连接日志标题触发入口。"""
        if self._dev_console_controller is not None:
            return

        self._dev_console_controller = DevConsoleController(
            queue_fill=self.executionInterface._debug_fill_mock_queue,
            queue_clear=self.executionInterface._debug_clear_mock_queue,
            queue_inspect=self.executionInterface._debug_inspect_queue,
        )

    def _show_dev_console(self) -> None:
        """显示隐藏开发控制台。"""
        self._init_dev_console()
        if self._dev_console_controller is None:
            return
        self._dev_console_controller.show_console_window(self)

    def eventFilter(self, obj, event):
        """在点击导航栏外部区域时自动收起已展开的导航栏。"""
        if event.type() == QEvent.Type.MouseButtonPress:
            # Check if the click is outside the navigation interface
            nav = self.navigationInterface
            if nav.width() > NAV_EXPANDED_WIDTH_THRESHOLD:
                # Get the click position relative to the navigation interface
                pos = nav.mapFromGlobal(event.globalPosition().toPoint())
                if not nav.rect().contains(pos):
                    nav.panel.collapse()
        return super().eventFilter(obj, event)

    def toggleTheme(self):
        """在亮色与暗色主题之间切换。"""
        theme = Theme.LIGHT if qconfig.theme == Theme.DARK else Theme.DARK
        qconfig.set(qconfig.themeMode, theme)

    def _connect_pages(self):
        """连接页面间的数据同步"""
        si = self.settingInterface
        hi = self.homeInterface
        cfg = si.config
        bind_shared_data_controller_signals(
            self._shared_data_controller,
            home_page=self.homeInterface,
            execution_page=self.executionInterface,
            overview_page=self.overviewInterface,
            feedback_parent=self,
            show_feedback=lambda **kwargs: show_feedback_infobar(
                **kwargs,
                position=InfoBarPosition.TOP,
            ),
            on_reconfigure_runtime_logging=lambda payload: apply_runtime_logging(
                payload=payload,
                execution_page=self.executionInterface,
            ),
        )

        # 路径改变时实时同步到首页
        si.game_path_changed.connect(hi.update_game_dir)
        si.output_path_changed.connect(hi.update_output_dir)
        si.wwiser_path_changed.connect(hi.update_wwiser)
        si.vgmstream_path_changed.connect(hi.update_vgmstream)
        hi.navigate_to_execution_requested.connect(lambda: self.switchTo(self.executionInterface))

        # 注入配置到各业务页面
        self.executionInterface.set_gui_config(cfg)
        self.overviewInterface.set_gui_config(cfg)
        self.overviewInterface.selection_sync_requested.connect(
            lambda payload: forward_selection_sync_feedback(
                payload=payload,
                execution_page=self.executionInterface,
                feedback_parent=self,
                show_feedback=lambda **kwargs: show_feedback_infobar(
                    **kwargs,
                    position=InfoBarPosition.TOP,
                ),
            )
        )
        self.executionInterface.output_state_refresh_requested.connect(
            self._shared_data_controller.refresh_shared_output_state
        )
        self.executionInterface.global_progress_state_changed.connect(
            lambda state: self._progress_strip_host.set_state(state, animate=True)
        )
        self.executionInterface.task_queue_busy_changed.connect(
            lambda busy: apply_task_queue_busy_state(
                busy=busy,
                setting_page=self.settingInterface,
                navigation_interface=self.navigationInterface,
                shared_data_controller=self._shared_data_controller,
            )
        )
        self.executionInterface.log_lines_appended.connect(self._log_drawer_controller.append_log_lines)
        self._progress_strip_host.set_state(
            self.executionInterface.current_global_progress_state(),
            animate=False,
        )
        self.settingInterface.shared_context_input_changed.connect(self._shared_data_controller.on_shared_context_input_changed)
        self.settingInterface.smooth_scroll_changed.connect(
            lambda page_enabled, widget_enabled: apply_smooth_scroll_settings(
                setting_page=self.settingInterface,
                home_page=self.homeInterface,
                about_page=self.aboutInterface,
                execution_page=self.executionInterface,
                overview_page=self.overviewInterface,
                log_output_widget=self._log_drawer_controller.output_widget,
                page_enabled=page_enabled,
                widget_enabled=widget_enabled,
            )
        )
        self.settingInterface.preview_audio_output_device_changed.connect(
            self.overviewInterface.set_preview_audio_output_device
        )
        self.settingInterface.preview_audio_volume_changed.connect(self.overviewInterface.set_preview_audio_volume)
        self.settingInterface.log_drawer_auto_collapse_changed.connect(
            self._log_drawer_controller.set_auto_collapse_enabled
        )
        self.settingInterface.log_levels_changed.connect(
            lambda payload: apply_runtime_logging(
                payload=payload,
                execution_page=self.executionInterface,
            )
        )
        apply_smooth_scroll_settings(
            setting_page=self.settingInterface,
            home_page=self.homeInterface,
            about_page=self.aboutInterface,
            execution_page=self.executionInterface,
            overview_page=self.overviewInterface,
            log_output_widget=self._log_drawer_controller.output_widget,
            page_enabled=cfg.page_smooth_scroll_enabled,
            widget_enabled=cfg.widget_smooth_scroll_enabled,
        )
        self._log_drawer_controller.set_auto_collapse_enabled(cfg.log_drawer_auto_collapse_enabled)
        sync_existing_runtime_logging(
            console_log_level=cfg.console_log_level,
            execution_page=self.executionInterface,
        )

        self._shared_data_controller.reader_signature = build_shared_entity_reader_signature(cfg)
        self._shared_data_controller.scan_signature = build_shared_entity_scan_signature(cfg)

        # 首页初始化完成后加载数据
        self._shared_data_controller.load_initial_data(cfg)

    def _has_active_background_work(self) -> bool:
        """返回窗口关闭前是否仍存在后台工作。"""
        home_page = getattr(self, "homeInterface", None)
        execution_page = getattr(self, "executionInterface", None)
        shared_controller = getattr(self, "_shared_data_controller", None)
        return bool(
            (home_page is not None and home_page.has_active_background_check())
            or (execution_page is not None and execution_page.has_active_background_task())
            or (
                shared_controller is not None
                and shared_controller.has_active_background_work()
            )
        )

    def _shutdown_background_work(self) -> None:
        """在窗口关闭前通知各后台 owner 收尾。"""
        home_page = getattr(self, "homeInterface", None)
        if home_page is not None:
            home_page.shutdown_background_check()
        execution_page = getattr(self, "executionInterface", None)
        if execution_page is not None:
            execution_page.shutdown_background_tasks()
        shared_controller = getattr(self, "_shared_data_controller", None)
        if shared_controller is not None:
            shared_controller.shutdown_background_work()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """在窗口尺寸变化时重排全局日志面板。"""
        super().resizeEvent(event)
        log_drawer_controller = getattr(self, "_log_drawer_controller", None)
        navigation_interface = getattr(self, "navigationInterface", None)
        if log_drawer_controller is None or navigation_interface is None:
            return
        log_drawer_controller.sync_host_rect(
            window_size=self.size(),
            navigation_width=navigation_interface.width(),
        )


