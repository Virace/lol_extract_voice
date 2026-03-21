from __future__ import annotations

from pathlib import Path
from time import perf_counter

from loguru import logger
from PySide6.QtCore import QEvent, QSize
from PySide6.QtGui import QIcon
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
from lol_audio_unpack.gui.service.worker import DataLoadWorker
from lol_audio_unpack.gui.view.about_page import AboutPage
from lol_audio_unpack.gui.view.home_page import HomePage
from lol_audio_unpack.gui.view.mapping_page import MappingPage
from lol_audio_unpack.gui.view.setting_page import SettingPage
from lol_audio_unpack.gui.view.unpack_page import UnpackPage
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

    def __init__(self):
        startup_begin = perf_counter()
        previous_mark = startup_begin
        super().__init__()
        previous_mark = _log_window_stage("FluentWindow 基类初始化", startup_begin, previous_mark)

        # apply specific real-time listeners for theme tracking
        qconfig.themeChanged.connect(setTheme)
        qconfig.themeColorChanged.connect(setThemeColor)
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
        self.unpackInterface = UnpackPage(self)
        previous_mark = _log_window_stage("UnpackPage 初始化完成", startup_begin, previous_mark)
        self.mappingInterface = MappingPage(self)
        previous_mark = _log_window_stage("MappingPage 初始化完成", startup_begin, previous_mark)
        self.aboutInterface = AboutPage(self)
        previous_mark = _log_window_stage("AboutPage 初始化完成", startup_begin, previous_mark)
        self._data_app_context = None
        self._is_loading_shared_data = False
        self._pending_refresh_notice = False

        self._initNavigation()
        previous_mark = _log_window_stage("导航初始化完成", startup_begin, previous_mark)
        self._initWindow()
        previous_mark = _log_window_stage("窗口属性初始化完成", startup_begin, previous_mark)

        # 连接设置页面和首页
        self._connect_pages()
        previous_mark = _log_window_stage("页面连接与首轮数据加载触发完成", startup_begin, previous_mark)

        self.splashScreen.finish()
        _log_window_stage("SplashScreen 结束", startup_begin, previous_mark)

    def _initNavigation(self):
        # add sub interface top
        self.addSubInterface(self.homeInterface, FIF.HOME, '主页')
        self.addSubInterface(self.unpackInterface, FIF.DOWNLOAD, '英雄解包')
        self.addSubInterface(self.mappingInterface, FIF.DOCUMENT, '事件映射')
        self.navigationInterface.addItem(
            routeKey='refreshSharedData',
            icon=FIF.SYNC,
            text='刷新数据',
            onClick=self._refresh_shared_output_data,
            selectable=False,
        )

        # add separator
        self.navigationInterface.addSeparator()

        # add custom widget to bottom
        self.navigationInterface.addItem(
            routeKey='themeSwitcher',
            icon=FIF.PALETTE,
            text='主题切换',
            onClick=self.toggleTheme,
            selectable=False,
            position=NavigationItemPosition.BOTTOM
        )

        self.addSubInterface(
            self.settingInterface, FIF.SETTING, '全局设置', position=NavigationItemPosition.BOTTOM)
        self.addSubInterface(
            self.aboutInterface, FIF.INFO, '关于', position=NavigationItemPosition.BOTTOM)

        self.navigationInterface.setExpandWidth(180)

    def _initWindow(self):
        self.resize(1130, 800)
        self.setMinimumWidth(860)
        self.setWindowIcon(QIcon(":/app_icon.png")) # Placeholder for icon
        self.setWindowTitle(f'Lol Audio Unpack  {__version__}')

        # Calculate screen center
        desktop = QApplication.primaryScreen().availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(int(w / 2 - self.width() / 2), int(h / 2 - self.height() / 2))

        # Install event filter to catch clicks outside the navigation bar
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):
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
            logger.info(f"日志系统已重定向到输出目录: {log_dir}")

        # 路径改变时实时同步到首页
        si.game_path_changed.connect(hi.update_game_dir)
        si.output_path_changed.connect(hi.update_output_dir)
        si.wwiser_path_changed.connect(hi.update_wwiser)
        si.vgmstream_path_changed.connect(hi.update_vgmstream)

        # 注入配置到各业务页面
        self.unpackInterface.set_gui_config(cfg)
        self.mappingInterface.set_gui_config(cfg)

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
            self._data_app_context = create_app_context(
                cli_overrides=cfg.to_app_context_overrides()
            )
            self.mappingInterface.set_app_context(self._data_app_context)
            logger.info("AppContext 创建成功")
        except Exception as e:
            self._is_loading_shared_data = False
            self._data_app_context = None
            self.mappingInterface.set_app_context(None)
            self.mappingInterface.clear_data()
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

        self.unpackInterface._cached_data["champions"] = data
        self.mappingInterface.set_entity_data("champions", data)

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

        self.unpackInterface._cached_data["maps"] = data
        self.mappingInterface.set_entity_data("maps", data)
        self._finish_data_loading()

        # 如果当前在解包页面，刷新显示
        if self.stackedWidget.currentWidget() == self.unpackInterface:
            current_key = self.unpackInterface.nav_pivot.currentRouteKey()
            logger.info(f"当前在解包页面，刷新显示: {current_key}")
            if current_key and self.unpackInterface._cached_data.get(current_key):
                self.unpackInterface.add_preview_data(self.unpackInterface._cached_data[current_key])
        else:
            logger.info("当前不在解包页面，等待切换时显示")

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
                content="解包页和事件映射页已同步到当前本地输出目录。",
                level="success",
            )
            self._pending_refresh_notice = False

    def _refresh_shared_output_data(self):
        """刷新解包页与事件映射页共用的本地输出数据。"""
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

    def _reload_unpack_data(self, cfg):
        """重新加载解包页与事件映射页共用的实体数据。"""
        self._data_app_context = None
        self.unpackInterface._cached_data = {"champions": [], "maps": []}
        self.mappingInterface.clear_data()
        self.mappingInterface.set_app_context(None)
        self.homeInterface.set_loading_state("正在重新加载数据…", active=True)
        self._load_initial_data(cfg)

    def _inject_mock_data(self):
        self.unpackInterface.add_preview_data([
            {"id": "1", "name": "Annie", "audio": "ready", "types": ["VO", "SFX"]},
            {"id": "103", "name": "Ahri", "audio": "cached", "types": ["VO", "SFX", "MUSIC"]},
            {"id": "222", "name": "Jinx", "audio": "ready", "types": ["VO", "SFX"]},
            {"id": "266", "name": "Aatrox", "audio": "staged", "types": ["VO", "SFX", "MUSIC"]},
            {"id": "350", "name": "Yuumi", "audio": "missing", "types": ["VO"]},
            {"id": "777", "name": "Yone", "audio": "ready", "types": ["VO", "SFX"]},
            {"id": "0", "name": "Common Map", "audio": "queued", "types": ["SFX"]},
            {"id": "11", "name": "SR Map", "audio": "cached", "types": ["VO", "SFX", "MUSIC"]},
        ])
