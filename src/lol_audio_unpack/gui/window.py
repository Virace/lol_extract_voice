"""应用主窗口与页面装配逻辑。"""

from __future__ import annotations

import sys
from pathlib import Path
from time import perf_counter

from loguru import logger
from PySide6.QtCore import QEvent, QRect, QSize, QTimer
from PySide6.QtGui import QIcon, QResizeEvent, QShowEvent
from PySide6.QtWidgets import QApplication
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
from lol_audio_unpack.app_context import create_app_context
from lol_audio_unpack.gui.common import apply_smooth_scroll_enabled
from lol_audio_unpack.gui.components.log_drawer import (
    GlobalLogDrawer,
    _build_log_panel_host_rect,
)
from lol_audio_unpack.gui.service.worker import DataLoadWorker
from lol_audio_unpack.gui.view.about_page import AboutPage
from lol_audio_unpack.gui.view.execution_page import ExecutionPage
from lol_audio_unpack.gui.view.home_page import HomePage
from lol_audio_unpack.gui.view.overview_page import OverviewPage
from lol_audio_unpack.gui.view.setting_page import SettingPage
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

        # create splash screen
        self.splashScreen = SplashScreen(self.windowIcon(), self)
        self.splashScreen.setIconSize(QSize(106, 106))
        self.splashScreen.raise_()
        previous_mark = _log_window_stage("SplashScreen 初始化完成", startup_begin, previous_mark)

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
        self._data_app_context = None
        self._is_loading_shared_data = False
        self._pending_refresh_notice = False
        self._window_material_bootstrapped = False

        self._initNavigation()
        previous_mark = _log_window_stage("导航初始化完成", startup_begin, previous_mark)
        self._initWindow()
        previous_mark = _log_window_stage("窗口属性初始化完成", startup_begin, previous_mark)
        self._init_global_log_panel()
        previous_mark = _log_window_stage("全局日志面板初始化完成", startup_begin, previous_mark)

        # 连接设置页面和首页
        self._connect_pages()
        previous_mark = _log_window_stage("页面连接与首轮数据加载触发完成", startup_begin, previous_mark)

        self.splashScreen.finish()
        _log_window_stage("SplashScreen 结束", startup_begin, previous_mark)

    def _initNavigation(self):
        """初始化主窗口导航项。"""
        # add sub interface top
        self.addSubInterface(self.homeInterface, FIF.HOME, "主页")
        self.addSubInterface(self.overviewInterface, FIF.DOCUMENT, "实体总览")
        self.addSubInterface(self.executionInterface, FIF.DOWNLOAD, "执行中心")
        self.navigationInterface.addItem(
            routeKey="refreshSharedData",
            icon=FIF.SYNC,
            text="刷新数据",
            onClick=self._refresh_shared_output_data,
            selectable=False,
        )

        # add separator
        self.navigationInterface.addSeparator()

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
        self.setWindowIcon(QIcon(":/app_icon.png"))  # Placeholder for icon
        self.setWindowTitle(f"Lol Audio Unpack  {__version__}")

        # Calculate screen center
        desktop = QApplication.primaryScreen().availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(int(w / 2 - self.width() / 2), int(h / 2 - self.height() / 2))

        # Install event filter to catch clicks outside the navigation bar
        QApplication.instance().installEventFilter(self)

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

        logger.debug(f"主窗口已启用 Mica Alt 材质效果: dark={is_dark_mode}")

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
        if event.type() in {
            QEvent.Type.WindowActivate,
            QEvent.Type.WindowDeactivate,
            QEvent.Type.WinIdChange,
        }:
            self._schedule_window_material_refresh()
        return super().event(event)

    def _init_global_log_panel(self) -> None:
        """初始化主窗口底部的全局日志抽屉。"""
        self._global_log_drawer = GlobalLogDrawer(self)
        self._global_log_drawer.set_log_text(self.executionInterface.current_log_text())
        self._global_log_drawer.sync_host_rect(self._current_log_panel_host_rect(), animate=False)

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

        # 如果配置了输出目录，重新初始化日志系统到该目录
        if cfg.output_path:
            log_dir = Path(cfg.output_path) / "logs"
            setup_logging(
                dev_mode=True,
                log_level="INFO",
                log_file_path=log_dir,
                show_function_info=True,
            )

        # 路径改变时实时同步到首页
        si.game_path_changed.connect(hi.update_game_dir)
        si.output_path_changed.connect(hi.update_output_dir)
        si.wwiser_path_changed.connect(hi.update_wwiser)
        si.vgmstream_path_changed.connect(hi.update_vgmstream)

        # 注入配置到各业务页面
        self.executionInterface.set_gui_config(cfg)
        self.overviewInterface.set_gui_config(cfg)
        self.overviewInterface.selection_sync_requested.connect(self._sync_selection_to_execution_center)
        self.executionInterface.refresh_requested.connect(self._refresh_shared_output_data)
        self.executionInterface.task_running_changed.connect(self._on_unpack_task_running_changed)
        self.executionInterface.log_lines_appended.connect(self._append_global_log_lines)
        self.executionInterface.attach_runtime_log_sink()
        self.settingInterface.smooth_scroll_changed.connect(self._apply_smooth_scroll_setting)
        self.settingInterface.log_drawer_auto_collapse_changed.connect(
            self._apply_log_drawer_auto_collapse_setting
        )
        self._apply_smooth_scroll_setting(
            cfg.page_smooth_scroll_enabled,
            cfg.widget_smooth_scroll_enabled,
        )
        self._apply_log_drawer_auto_collapse_setting(cfg.log_drawer_auto_collapse_enabled)

        if cfg.output_path:
            logger.info(f"日志系统已重定向到输出目录: {log_dir}")

        # 配置变更时重新加载数据
        si.game_path_changed.connect(lambda: self._reload_unpack_data(cfg))
        si.output_path_changed.connect(lambda: self._reload_unpack_data(cfg))

        # 首页初始化完成后加载数据
        logger.info("准备加载初始数据...")
        hi.set_loading_state("正在加载实体数据…", active=True)
        self._load_initial_data(cfg)

    def _load_initial_data(self, cfg):
        """程序启动时加载实体数据"""
        logger.info("开始加载初始数据...")
        self._is_loading_shared_data = True

        try:
            logger.debug(f"当前配置: output_path={cfg.output_path}, game_path={cfg.game_path}")
            self._data_app_context = create_app_context(cli_overrides=cfg.to_app_context_overrides())
            self.overviewInterface.set_app_context(self._data_app_context)
            self.executionInterface.clear_entity_data()
            logger.info("AppContext 创建成功")
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

        logger.info("启动 champions 数据加载线程")
        self._champions_worker = DataLoadWorker(self._data_app_context, "champions")
        self._champions_worker.finished.connect(self._on_champions_loaded)
        self._champions_worker.error.connect(self._on_data_load_error)
        self._champions_worker.start()

    def _on_champions_loaded(self, data):
        """Champions 数据加载完成"""
        logger.info(f"Champions 数据加载完成，共 {len(data)} 条")

        self.executionInterface.set_entity_data("champions", data)
        self.overviewInterface.set_entity_data("champions", data)

        # 继续加载 maps 数据
        if self._data_app_context is None:
            logger.error("AppContext 未初始化，无法继续加载 maps 数据")
            self._finish_data_loading()
            return

        logger.info("启动 maps 数据加载")
        self._maps_worker = DataLoadWorker(self._data_app_context, "maps")
        self._maps_worker.finished.connect(self._on_maps_loaded)
        self._maps_worker.error.connect(self._on_data_load_error)
        self._maps_worker.start()

    def _on_maps_loaded(self, data):
        """Maps 数据加载完成"""
        logger.info(f"Maps 数据加载完成，共 {len(data)} 条")

        self.executionInterface.set_entity_data("maps", data)
        self.overviewInterface.set_entity_data("maps", data)
        self._finish_data_loading()

    def _on_data_load_error(self, error):
        """数据加载失败"""
        self._is_loading_shared_data = False
        self.homeInterface.set_loading_state(f"加载失败: {error}", active=False)
        if self._pending_refresh_notice:
            self._show_refresh_infobar(
                title="刷新失败",
                content=str(error),
                level="error",
            )
            self._pending_refresh_notice = False

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

    def _on_unpack_task_running_changed(self, running: bool) -> None:
        """同步解包任务运行态到共享配置页面。"""
        self.settingInterface.setEnabled(not running)

    def _append_global_log_lines(self, lines: tuple[str, ...]) -> None:
        """向主窗口级日志抽屉增量追加一批日志。"""
        self._global_log_drawer.append_log_lines(lines)

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

    def _refresh_shared_output_data(self):
        """刷新解包页与事件映射页共用的本地输出数据。"""
        if self.executionInterface.is_task_running():
            logger.info("执行中心任务进行中，忽略共享刷新请求")
            InfoBar.warning(
                title="任务进行中",
                content="请等待当前任务结束后再刷新列表数据。",
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2500,
                parent=self,
            )
            return
        if self._is_loading_shared_data:
            logger.info("共享数据仍在加载中，忽略重复刷新请求")
            return

        self._pending_refresh_notice = True
        self._reload_unpack_data(self.settingInterface.config)

    def _show_refresh_infobar(self, *, title: str, content: str, level: str) -> None:
        """在共享刷新完成后展示 InfoBar 通知。"""
        factory = InfoBar.success if level == "success" else InfoBar.error
        factory(
            title=title,
            content=content,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=2500,
            parent=self,
        )

    def _sync_selection_to_execution_center(self, payload) -> None:
        """以全局反馈方式处理中总览到执行中心的同步。"""
        summary = self.executionInterface.set_selected_entities(payload, feedback_parent=self)
        if summary is None:
            return

        InfoBar.success(
            title="已同步到执行中心",
            content=summary,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=2500,
            parent=self,
        )

    def _reload_unpack_data(self, cfg):
        """重新加载解包页与事件映射页共用的实体数据。"""
        self._data_app_context = None
        self.executionInterface.clear_entity_data()
        self.overviewInterface.clear_data()
        self.overviewInterface.set_app_context(None)
        self.homeInterface.set_loading_state("正在重新加载数据…", active=True)
        self._load_initial_data(cfg)

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
