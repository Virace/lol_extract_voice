"""应用主窗口与页面装配逻辑。"""

from __future__ import annotations

import sys
from pathlib import Path
from time import perf_counter

from loguru import logger
from PySide6.QtCore import QEvent, QPoint, QRect, QSize, QThreadPool, QTimer
from PySide6.QtGui import QCloseEvent, QIcon, QResizeEvent, QShowEvent
from PySide6.QtWidgets import QApplication, QMessageBox
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
from lol_audio_unpack.app_context import OperationOptions, create_app_context
from lol_audio_unpack.facade import LolAudioUnpackApp
from lol_audio_unpack.gui.common import (
    apply_smooth_scroll_enabled,
    load_app_icon,
    show_feedback_infobar,
)
from lol_audio_unpack.gui.components.dev_console import DevConsoleWindow
from lol_audio_unpack.gui.components.log_drawer import (
    GlobalLogDrawer,
    _build_log_panel_host_rect,
)
from lol_audio_unpack.gui.service.data_loader import EntityDataLoader
from lol_audio_unpack.gui.service.worker import DataLoadWorker
from lol_audio_unpack.gui.task_models import OutputStateRefreshRequest
from lol_audio_unpack.gui.view.about_page import AboutPage
from lol_audio_unpack.gui.view.execution_page import ExecutionPage
from lol_audio_unpack.gui.view.home_page import HomePage
from lol_audio_unpack.gui.view.overview_page import OverviewPage
from lol_audio_unpack.gui.view.setting_page import SettingPage
from lol_audio_unpack.gui.workers import TaskWorker
from lol_audio_unpack.manager.data_reader import DataReader
from lol_audio_unpack.utils.common import Singleton
from lol_audio_unpack.utils.logging import setup_logging

NAV_EXPANDED_WIDTH_THRESHOLD = 100
DEV_CONSOLE_COMMAND_MIN_PARTS = 2
DEV_CONSOLE_QUEUE_FILL_PARTS = 3


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


def _prepare_shared_entity_data(cli_overrides: dict[str, str | bool]) -> None:
    """为实体列表准备后端共享数据。"""
    app_context = create_app_context(cli_overrides=cli_overrides)
    app_context.runtime_cache["disable_terminal_progress"] = True
    app = LolAudioUnpackApp(app_context)
    app.update(OperationOptions(), target="all")


def _reset_data_reader_singleton() -> None:
    """重置 ``DataReader`` 单例，确保后续读取使用新的上下文。"""
    if DataReader in Singleton._instances:
        logger.debug("检测到共享实体数据读取上下文已变化，重置 DataReader 单例缓存")
        del Singleton._instances[DataReader]


def _build_shared_entity_reader_signature(cfg) -> tuple[str | bool, ...]:
    """构建影响共享实体数据读取上下文的配置签名。"""
    overrides = cfg.to_app_context_overrides()
    return (
        overrides["SOURCE_MODE"],
        overrides["GAME_PATH"],
        overrides["GAME_REGION"],
        overrides["REMOTE_LIVE_REGION"],
        overrides["REMOTE_VERSION"],
        overrides["REMOTE_LCU_MANIFEST_URL"],
        overrides["REMOTE_GAME_MANIFEST_URL"],
    )


def _build_shared_entity_scan_signature(cfg) -> tuple[str | bool, ...]:
    """构建仅影响输出扫描结果的配置签名。"""
    overrides = cfg.to_app_context_overrides()
    return (
        overrides["OUTPUT_PATH"],
        overrides["GROUP_BY_TYPE"],
    )


class MainWindow(FluentWindow):
    """应用主窗口。"""

    def __init__(self):
        startup_begin = perf_counter()
        previous_mark = startup_begin
        super().__init__()
        previous_mark = _log_window_stage("FluentWindow 基类初始化", startup_begin, previous_mark)

        # apply specific real-time listeners for theme tracking
        qconfig.themeChanged.connect(setTheme)
        qconfig.themeColorChanged.connect(setThemeColor)
        qconfig.themeChanged.connect(lambda _theme: self._try_enable_window_material())
        previous_mark = _log_window_stage("主题变更信号连接完成", startup_begin, previous_mark)

        self._data_app_context = None
        self._is_loading_shared_data = False
        self._is_preparing_shared_data = False
        self._pending_refresh_notice = False
        self._pending_runtime_entity_refresh = False
        self._pending_runtime_entity_refresh_allow_auto_prepare = False
        self._pending_runtime_entity_refresh_reset_reader = False
        self._allow_auto_prepare_on_shared_reload = True
        self._shared_data_auto_prepare_attempted = False
        self._shared_data_prepare_worker: TaskWorker | None = None
        self._shared_entity_reader_signature: tuple[str | bool, ...] | None = None
        self._shared_entity_scan_signature: tuple[str | bool, ...] | None = None
        self._window_material_bootstrapped = False
        self._last_window_material_logged_state: bool | None = None
        self._dev_console: DevConsoleWindow | None = None
        self._app_event_filter_host = QApplication.instance()
        self._app_event_filter_installed = False
        self._runtime_entity_refresh_timer = QTimer(self)
        self._runtime_entity_refresh_timer.setSingleShot(True)
        self._runtime_entity_refresh_timer.setInterval(900)
        self._runtime_entity_refresh_timer.timeout.connect(self._flush_pending_runtime_entity_refresh)
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

        self._initNavigation()
        previous_mark = _log_window_stage("导航初始化完成", startup_begin, previous_mark)
        self._init_global_log_panel()
        previous_mark = _log_window_stage("全局日志面板初始化完成", startup_begin, previous_mark)

        # 连接设置页面和首页
        self._connect_pages()
        previous_mark = _log_window_stage("页面连接与首轮数据加载触发完成", startup_begin, previous_mark)
        return previous_mark

    def _initNavigation(self):
        """初始化主窗口导航项。"""
        # add sub interface top
        self.addSubInterface(self.homeInterface, FIF.HOME, "主页")
        self.addSubInterface(self.executionInterface, FIF.DOWNLOAD, "执行中心")
        self.addSubInterface(self.overviewInterface, FIF.DOCUMENT, "实体总览")

        self.navigationInterface.addSeparator()

        self.navigationInterface.addItem(
            routeKey="refreshSharedData",
            icon=FIF.SYNC,
            text="刷新数据",
            onClick=self._refresh_shared_output_state,
            selectable=False,
        )

        # add custom widget to bottom
        self.navigationInterface.addItem(
            routeKey="themeSwitcher",
            icon=FIF.PALETTE,
            text="主题切换",
            onClick=self.toggleTheme,
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
        )

        self.addSubInterface(self.settingInterface, FIF.SETTING, "全局设置", position=NavigationItemPosition.BOTTOM)
        self.addSubInterface(self.aboutInterface, FIF.INFO, "关于", position=NavigationItemPosition.BOTTOM)

        self.navigationInterface.setExpandWidth(180)

    def _initWindow(self):
        """设置主窗口尺寸、标题与基础事件过滤器。"""
        self.resize(1130, 800)
        self.setMinimumWidth(860)
        self.setWindowIcon(load_app_icon())
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
        self._unregister_app_event_filter()
        super().closeEvent(event)

    def _init_global_log_panel(self) -> None:
        """初始化主窗口底部的全局日志抽屉。"""
        self._global_log_drawer = GlobalLogDrawer(self)
        self._global_log_drawer.set_log_text(self.executionInterface.current_log_text())
        self._global_log_drawer.dev_console_requested.connect(self._show_dev_console)
        self._global_log_drawer.sync_host_rect(self._current_log_panel_host_rect(), animate=False)

    def _init_dev_console(self) -> None:
        """按需初始化隐藏开发控制台并连接日志标题触发入口。"""
        if self._dev_console is not None:
            return

        self._dev_console = DevConsoleWindow(self)
        self._dev_console.command_submitted.connect(self._handle_dev_console_command)

    def _show_dev_console(self) -> None:
        """显示隐藏开发控制台。"""
        self._init_dev_console()
        if self._dev_console is None:
            return
        self._position_dev_console()
        self._dev_console.show()
        self._dev_console.raise_()
        self._dev_console.activateWindow()
        self._dev_console.focus_command_input()

    def _position_dev_console(self) -> None:
        """将开发控制台定位到主窗口右下角附近。"""
        if self._dev_console is None:
            return

        if self._dev_console.width() <= 0 or self._dev_console.height() <= 0:
            self._dev_console.resize(self._dev_console.sizeHint())

        offset_x = max(self.width() - self._dev_console.width() - 32, 0)
        offset_y = max(self.height() - self._dev_console.height() - 48, 0)
        anchor = self.mapToGlobal(QPoint(offset_x, offset_y))
        self._dev_console.move(anchor)

    def _handle_dev_console_command(self, command: str) -> None:
        """执行开发控制台命令并回写输出。"""
        if self._dev_console is None:
            return

        self._dev_console.append_output(f"> {command}")
        try:
            output_lines = self._execute_dev_console_command(command)
        except ValueError as exc:
            self._dev_console.append_output(f"ERROR: {exc}")
            return

        for line in output_lines:
            self._dev_console.append_output(line)

    def _execute_dev_console_command(self, command: str) -> tuple[str, ...]:
        """解析并执行开发控制台命令。"""
        normalized = command.strip()
        if not normalized:
            raise ValueError("空命令，输入 help 查看可用命令。")

        parts = normalized.split()
        keyword = parts[0].lower()
        if keyword == "help":
            return (
                "可用命令:",
                "help",
                "queue fill <n>",
                "queue clear",
                "queue inspect",
            )

        if keyword != "queue" or len(parts) < DEV_CONSOLE_COMMAND_MIN_PARTS:
            raise ValueError("未知命令，输入 help 查看可用命令。")

        action = parts[1].lower()
        if action == "fill":
            if len(parts) != DEV_CONSOLE_QUEUE_FILL_PARTS or not parts[2].isdigit():
                raise ValueError("queue fill 需要一个正整数参数。")
            result = self.executionInterface._debug_fill_mock_queue(int(parts[2]))
            return (result,)
        if action == "clear":
            return (self.executionInterface._debug_clear_mock_queue(),)
        if action == "inspect":
            return tuple(self.executionInterface._debug_inspect_queue().splitlines())

        raise ValueError("未知 queue 子命令，输入 help 查看可用命令。")

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

        # 路径改变时实时同步到首页
        si.game_path_changed.connect(hi.update_game_dir)
        si.output_path_changed.connect(hi.update_output_dir)
        si.wwiser_path_changed.connect(hi.update_wwiser)
        si.vgmstream_path_changed.connect(hi.update_vgmstream)

        # 注入配置到各业务页面
        self.executionInterface.set_gui_config(cfg)
        self.overviewInterface.set_gui_config(cfg)
        self.overviewInterface.selection_sync_requested.connect(self._sync_selection_to_execution_center)
        self.executionInterface.output_state_refresh_requested.connect(self._refresh_shared_output_state)
        self.executionInterface.task_queue_busy_changed.connect(self._on_task_queue_busy_changed)
        self.executionInterface.log_lines_appended.connect(self._append_global_log_lines)
        self.settingInterface.shared_context_input_changed.connect(self._on_shared_context_input_changed)
        self.settingInterface.smooth_scroll_changed.connect(self._apply_smooth_scroll_setting)
        self.settingInterface.log_drawer_auto_collapse_changed.connect(
            self._apply_log_drawer_auto_collapse_setting
        )
        self.settingInterface.log_levels_changed.connect(self._reconfigure_runtime_logging)
        self._apply_smooth_scroll_setting(
            cfg.page_smooth_scroll_enabled,
            cfg.widget_smooth_scroll_enabled,
        )
        self._apply_log_drawer_auto_collapse_setting(cfg.log_drawer_auto_collapse_enabled)
        self._reconfigure_runtime_logging(cfg)

        self._shared_entity_reader_signature = _build_shared_entity_reader_signature(cfg)
        self._shared_entity_scan_signature = _build_shared_entity_scan_signature(cfg)

        # 首页初始化完成后加载数据
        logger.debug("准备触发首轮共享实体数据加载")
        hi.set_loading_state("正在加载实体数据…", active=True)
        self._load_initial_data(cfg)

    def _load_initial_data(self, cfg):
        """程序启动时加载实体数据"""
        logger.info("开始加载共享实体数据")
        self._is_loading_shared_data = True

        try:
            logger.debug(f"当前配置: output_path={cfg.output_path}, game_path={cfg.game_path}")
            self._data_app_context = create_app_context(cli_overrides=cfg.to_app_context_overrides())
            self.overviewInterface.set_app_context(self._data_app_context)
            self.executionInterface.clear_entity_data()
            logger.debug("共享数据 AppContext 创建成功")
        except Exception as e:
            self._is_loading_shared_data = False
            self._data_app_context = None
            self.overviewInterface.set_app_context(None)
            self.overviewInterface.clear_data()
            self.executionInterface.clear_entity_data()
            logger.error(f"创建 AppContext 失败: {e}")
            self.homeInterface.set_loading_state("数据加载失败", active=False)
            if self._pending_refresh_notice:
                self._show_refresh_infobar(
                    title="刷新失败",
                    content=str(e),
                    level="error",
                )
                self._pending_refresh_notice = False
            return

        logger.debug("准备启动 champions 实体状态扫描线程")
        self._champions_worker = DataLoadWorker(self._data_app_context, "champions")
        self._champions_worker.finished.connect(self._on_champions_loaded)
        self._champions_worker.error.connect(self._on_data_load_error)
        self._champions_worker.start()

    def _on_champions_loaded(self, data):
        """Champions 数据加载完成"""
        logger.info(f"champions 实体列表已刷新，当前展示 {len(data)} 项")

        self.executionInterface.set_entity_data("champions", data)
        self.overviewInterface.set_entity_data("champions", data)

        # 继续加载 maps 数据
        if self._data_app_context is None:
            logger.error("AppContext 未初始化，无法继续加载 maps 数据")
            self._finish_data_loading()
            return

        logger.debug("准备启动 maps 实体状态扫描线程")
        self._maps_worker = DataLoadWorker(self._data_app_context, "maps")
        self._maps_worker.finished.connect(self._on_maps_loaded)
        self._maps_worker.error.connect(self._on_data_load_error)
        self._maps_worker.start()

    def _on_maps_loaded(self, data):
        """Maps 数据加载完成"""
        logger.info(f"maps 实体列表已刷新，当前展示 {len(data)} 项")

        self.executionInterface.set_entity_data("maps", data)
        self.overviewInterface.set_entity_data("maps", data)
        self._finish_data_loading()

    def _on_data_load_error(self, error):
        """数据加载失败"""
        self._is_loading_shared_data = False
        if (
            self._allow_auto_prepare_on_shared_reload
            and not self._shared_data_auto_prepare_attempted
            and self._should_auto_prepare_shared_data(str(error))
        ):
            self._shared_data_auto_prepare_attempted = True
            logger.info("共享数据缺失或版本不兼容，转入后台数据准备流程")
            self.homeInterface.set_loading_state("正在刷新基础数据…", active=True)
            self._start_shared_data_prepare(self.settingInterface.config)
            return
        self.homeInterface.set_loading_state(f"加载失败: {error}", active=False)
        if self._pending_refresh_notice:
            self._show_refresh_infobar(
                title="刷新失败",
                content=str(error),
                level="error",
            )
            self._pending_refresh_notice = False
        self._flush_pending_runtime_entity_refresh()

    def _finish_data_loading(self):
        """完成数据加载"""
        self._is_loading_shared_data = False
        self.homeInterface.set_loading_state("实体数据已就绪", active=False)
        if self._pending_refresh_notice:
            self._show_refresh_infobar(
                title="数据已刷新",
                content="实体总览与执行中心摘要已同步到当前本地输出目录。",
                level="success",
            )
            self._pending_refresh_notice = False
        self._flush_pending_runtime_entity_refresh()

    def _on_task_queue_busy_changed(self, busy: bool) -> None:
        """在任务队列忙碌状态变化时同步设置页锁定与延迟刷新。"""
        self.settingInterface.set_runtime_config_locked(busy)
        refresh_widget = self.navigationInterface.widget("refreshSharedData")
        if refresh_widget is not None:
            refresh_widget.setEnabled(not busy)
        if busy:
            self._runtime_entity_refresh_timer.stop()
            return
        self._flush_pending_runtime_entity_refresh()

    def _append_global_log_lines(self, lines: tuple[str, ...]) -> None:
        """向主窗口级日志抽屉增量追加一批日志。"""
        self._global_log_drawer.append_log_lines(lines)

    def _reconfigure_runtime_logging(self, cfg) -> None:
        """将运行时日志输出切换到当前输出目录，并重挂 GUI sink。"""
        log_dir = None
        if cfg.output_path:
            log_dir = Path(cfg.output_path) / "logs"
        setup_logging(
            dev_mode=True,
            log_level=cfg.console_log_level,
            file_log_level=cfg.file_log_level,
            log_file_path=log_dir,
            show_function_info=True,
        )
        self.executionInterface.attach_runtime_log_sink(cfg.console_log_level)
        if log_dir is not None:
            logger.debug(f"日志系统已重定向到输出目录: {log_dir}")
        else:
            logger.debug("日志系统已切换为仅控制台输出。")

    def _apply_log_drawer_auto_collapse_setting(self, enabled: bool) -> None:
        """应用日志抽屉点击外部自动收起设置。"""
        self._global_log_drawer.set_auto_collapse_enabled(enabled)

    def _current_log_panel_host_rect(self) -> QRect:
        """返回当前主窗口中可用于日志面板的页面内容区。"""
        return _build_log_panel_host_rect(self.size(), self.navigationInterface.width())

    def _apply_smooth_scroll_setting(self, page_enabled: bool, widget_enabled: bool) -> None:
        """统一应用 GUI 的平滑滚动配置。"""
        apply_smooth_scroll_enabled(self.settingInterface, page_enabled)
        apply_smooth_scroll_enabled(self.homeInterface, page_enabled)
        apply_smooth_scroll_enabled(self.aboutInterface, page_enabled)
        self.executionInterface.set_smooth_scroll_enabled(
            page_enabled=page_enabled,
            widget_enabled=widget_enabled,
        )
        self.overviewInterface.set_smooth_scroll_enabled(widget_enabled)
        apply_smooth_scroll_enabled(self._global_log_drawer.output_widget, widget_enabled)

    def _refresh_shared_output_state(self, refresh_request: object | None = None):
        """仅刷新解包产物对应的实体检测状态与输出扫描结果。"""
        self._reconfigure_runtime_logging(self.settingInterface.config)
        if self.executionInterface.has_incomplete_tasks():
            logger.debug("执行中心仍有未完成任务，忽略共享刷新请求")
            show_feedback_infobar(
                title="队列未清空",
                content="请等待当前任务队列全部结束后再刷新列表数据。",
                parent=self,
                level="warning",
                position=InfoBarPosition.TOP,
            )
            return
        if self._is_loading_shared_data or self._is_preparing_shared_data:
            logger.debug("共享数据仍在加载中，忽略重复刷新请求")
            return

        request = refresh_request if isinstance(refresh_request, OutputStateRefreshRequest) else None
        self._pending_refresh_notice = True
        if self._data_app_context is None:
            logger.info("共享上下文尚未就绪，回退到完整共享数据刷新")
            self._request_shared_data_reload(show_notice=True, allow_auto_prepare=True)
            return

        if request is not None and not request.requires_full_refresh and request.has_incremental_targets():
            logger.info("开始增量刷新共享输出状态")
            try:
                loader = EntityDataLoader(self._data_app_context)
                if request.champion_ids:
                    champion_rows = loader.load_entities_by_ids("champions", request.champion_ids)
                    self.executionInterface.update_entity_rows("champions", champion_rows)
                    self.overviewInterface.update_entity_rows("champions", champion_rows)
                if request.map_ids:
                    map_rows = loader.load_entities_by_ids("maps", request.map_ids)
                    self.executionInterface.update_entity_rows("maps", map_rows)
                    self.overviewInterface.update_entity_rows("maps", map_rows)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"增量刷新共享输出状态失败，回退到全量刷新: {exc}")
                self._request_shared_data_reload(show_notice=True, allow_auto_prepare=True)
                return

            if self._pending_refresh_notice:
                self._show_refresh_infobar(
                    title="数据已刷新",
                    content="受影响实体的状态已按任务结果增量更新。",
                    level="success",
                )
                self._pending_refresh_notice = False
            return

        logger.info("开始刷新共享输出状态")
        self._allow_auto_prepare_on_shared_reload = False
        self._shared_data_auto_prepare_attempted = False
        self._is_loading_shared_data = True
        self.homeInterface.set_loading_state("正在刷新输出状态…", active=True)
        self._champions_worker = DataLoadWorker(self._data_app_context, "champions")
        self._champions_worker.finished.connect(self._on_champions_loaded)
        self._champions_worker.error.connect(self._on_data_load_error)
        self._champions_worker.start()

    def _show_refresh_infobar(self, *, title: str, content: str, level: str) -> None:
        """在共享刷新完成后展示 InfoBar 通知。"""
        show_feedback_infobar(
            title=title,
            content=content,
            parent=self,
            level=level,
            position=InfoBarPosition.TOP,
        )

    def _sync_selection_to_execution_center(self, payload) -> None:
        """以全局反馈方式处理中总览到执行中心的同步。"""
        summary = self.executionInterface.set_selected_entities(payload, feedback_parent=self)
        if summary is None:
            return

        show_feedback_infobar(
            title="已同步到执行中心",
            content=summary,
            parent=self,
            level="success",
            position=InfoBarPosition.TOP,
        )

    def _reload_unpack_data(self, cfg):
        """重新加载解包页与事件映射页共用的实体数据。"""
        self._data_app_context = None
        self.executionInterface.clear_entity_data()
        self.overviewInterface.clear_data()
        self.overviewInterface.set_app_context(None)
        self.homeInterface.set_loading_state("正在重新加载数据…", active=True)
        self._load_initial_data(cfg)

    def _on_shared_context_input_changed(self) -> None:
        """根据共享上下文输入变化类型安排共享实体数据刷新。"""
        cfg = self.settingInterface.config
        current_reader_signature = _build_shared_entity_reader_signature(cfg)
        current_scan_signature = _build_shared_entity_scan_signature(cfg)
        reader_changed = current_reader_signature != self._shared_entity_reader_signature
        scan_changed = current_scan_signature != self._shared_entity_scan_signature

        if scan_changed:
            self._reconfigure_runtime_logging(cfg)

        self._shared_entity_reader_signature = current_reader_signature
        self._shared_entity_scan_signature = current_scan_signature

        if not reader_changed and not scan_changed:
            return

        self._pending_runtime_entity_refresh = True
        self._pending_runtime_entity_refresh_allow_auto_prepare = (
            self._pending_runtime_entity_refresh_allow_auto_prepare or reader_changed
        )
        self._pending_runtime_entity_refresh_reset_reader = (
            self._pending_runtime_entity_refresh_reset_reader or reader_changed
        )
        self._schedule_runtime_entity_refresh()

    def _schedule_runtime_entity_refresh(self) -> None:
        """为运行时配置变更安排一次共享实体数据刷新。"""
        if self.executionInterface.has_incomplete_tasks():
            logger.debug("任务队列未清空，延后处理运行时配置对应的实体数据刷新")
            return
        if self._is_loading_shared_data or self._is_preparing_shared_data:
            logger.debug("共享数据刷新仍在进行中，保留待处理的运行时配置刷新")
            return
        self._runtime_entity_refresh_timer.start()

    def _flush_pending_runtime_entity_refresh(self) -> None:
        """在合适时机执行因运行时配置变更而待处理的实体数据刷新。"""
        if not self._pending_runtime_entity_refresh:
            return
        if self.executionInterface.has_incomplete_tasks():
            return
        if self._is_loading_shared_data or self._is_preparing_shared_data:
            return
        allow_auto_prepare = self._pending_runtime_entity_refresh_allow_auto_prepare
        reset_reader = self._pending_runtime_entity_refresh_reset_reader
        self._pending_runtime_entity_refresh = False
        self._pending_runtime_entity_refresh_allow_auto_prepare = False
        self._pending_runtime_entity_refresh_reset_reader = False
        if reset_reader:
            _reset_data_reader_singleton()
        self._request_shared_data_reload(show_notice=False, allow_auto_prepare=allow_auto_prepare)

    def _request_shared_data_reload(self, *, show_notice: bool, allow_auto_prepare: bool) -> None:
        """启动一次共享实体数据刷新流程。"""
        self._pending_refresh_notice = show_notice
        self._allow_auto_prepare_on_shared_reload = allow_auto_prepare
        self._shared_data_auto_prepare_attempted = False
        self._reload_unpack_data(self.settingInterface.config)

    def _should_auto_prepare_shared_data(self, error: str) -> bool:
        """判断当前共享数据加载错误是否适合自动补一次后端更新。"""
        normalized = str(error)
        return (
            "请先运行更新程序" in normalized
            or "请立即运行数据更新程序" in normalized
            or "核心数据文件" in normalized
            or "数据版本与游戏版本严重不匹配" in normalized
        )

    def _start_shared_data_prepare(self, cfg) -> None:
        """在后台线程中补齐共享实体数据所需的后端更新。"""
        if self._shared_data_prepare_worker is not None:
            return

        overrides = dict(cfg.to_app_context_overrides())

        def run_prepare() -> None:
            _prepare_shared_entity_data(overrides)

        worker = TaskWorker(run_prepare)
        worker.signals.started.connect(self._on_shared_data_prepare_started)
        worker.signals.finished.connect(lambda _result, current_cfg=cfg: self._on_shared_data_prepare_finished(current_cfg))
        worker.signals.failed.connect(self._on_shared_data_prepare_failed)
        self._shared_data_prepare_worker = worker
        QThreadPool.globalInstance().start(worker)

    def _on_shared_data_prepare_started(self) -> None:
        """同步后台共享数据准备开始时的界面状态。"""
        self._is_preparing_shared_data = True
        self.homeInterface.set_loading_state("正在刷新基础数据…", active=True)

    def _on_shared_data_prepare_finished(self, cfg) -> None:
        """在后台数据准备结束后重新加载共享实体数据。"""
        self._is_preparing_shared_data = False
        self._shared_data_prepare_worker = None
        self._reload_unpack_data(cfg)

    def _on_shared_data_prepare_failed(self, error: str) -> None:
        """处理后台共享数据准备失败后的界面状态。"""
        self._is_preparing_shared_data = False
        self._shared_data_prepare_worker = None
        self.homeInterface.set_loading_state(f"加载失败: {error}", active=False)
        if self._pending_refresh_notice:
            self._show_refresh_infobar(
                title="刷新失败",
                content=error,
                level="error",
            )
            self._pending_refresh_notice = False

    def _inject_mock_data(self):
        mock_rows = [
            {"id": "1", "name": "Annie", "alias": "annie", "audio": "已存在", "mapping": "未存在"},
            {"id": "103", "name": "Ahri", "alias": "ahri", "audio": "已存在", "mapping": "已存在"},
            {"id": "222", "name": "Jinx", "alias": "jinx", "audio": "未存在", "mapping": "未存在"},
            {"id": "11", "name": "Summoner's Rift", "alias": "sr", "audio": "已存在", "mapping": "已存在"},
        ]
        self.overviewInterface.set_entity_data("champions", mock_rows[:3])
        self.overviewInterface.set_entity_data("maps", mock_rows[3:])
        self.executionInterface.set_entity_data("champions", mock_rows[:3])
        self.executionInterface.set_entity_data("maps", mock_rows[3:])

    def resizeEvent(self, event: QResizeEvent) -> None:
        """在窗口尺寸变化时重排全局日志面板。"""
        super().resizeEvent(event)
        if not hasattr(self, "_global_log_drawer"):
            return
        self._global_log_drawer.sync_host_rect(self._current_log_panel_host_rect(), animate=False)
