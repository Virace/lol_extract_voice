from __future__ import annotations

from PySide6.QtCore import Qt, QSize, QEvent
from PySide6.QtGui import QIcon, QColor
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout

from qfluentwidgets import (
    FluentWindow,
    NavigationItemPosition,
    SplashScreen,
    SubtitleLabel,
    setTheme,
    setThemeColor,
    qconfig,
    Theme
)
from qfluentwidgets import FluentIcon as FIF

from lol_audio_unpack import __version__
from lol_audio_unpack.gui.view.home_page import HomePage
from lol_audio_unpack.gui.view.unpack_page import UnpackPage
from lol_audio_unpack.gui.view.mapping_page import MappingPage
from lol_audio_unpack.gui.view.setting_page import SettingPage
from lol_audio_unpack.gui.view.about_page import AboutPage


class MainWindow(FluentWindow):

    def __init__(self):
        super().__init__()
        
        # apply specific real-time listeners for theme tracking
        qconfig.themeChanged.connect(setTheme)
        qconfig.themeColorChanged.connect(setThemeColor)

        
        # create splash screen
        self.splashScreen = SplashScreen(self.windowIcon(), self)
        self.splashScreen.setIconSize(QSize(106, 106))
        self.splashScreen.raise_()

        # create sub interface — SettingPage first so cfg is ready
        self.settingInterface = SettingPage(self)
        cfg = self.settingInterface.config

        self.homeInterface = HomePage(cfg, self)
        self.unpackInterface = UnpackPage(self)
        self.mappingInterface = MappingPage(self)
        self.aboutInterface = AboutPage(self)

        self._initNavigation()
        self._initWindow()

        # 连接设置页面和首页
        self._connect_pages()

        self.splashScreen.finish()

    def _initNavigation(self):
        # add sub interface top
        self.addSubInterface(self.homeInterface, FIF.HOME, '主页')
        self.addSubInterface(self.unpackInterface, FIF.DOWNLOAD, '英雄解包')
        self.addSubInterface(self.mappingInterface, FIF.DOCUMENT, '资源映射')
        
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
            if nav.width() > 100:  # If wider than typical compact 48px size
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
        print("=== _connect_pages 被调用 ===")
        from loguru import logger

        logger.info("_connect_pages 被调用")

        si = self.settingInterface
        hi = self.homeInterface
        cfg = si.config

        # 路径改变时实时同步到首页
        si.game_path_changed.connect(hi.update_game_dir)
        si.output_path_changed.connect(hi.update_output_dir)
        si.wwiser_path_changed.connect(hi.update_wwiser)
        si.vgmstream_path_changed.connect(hi.update_vgmstream)

        # 注入配置到解包页面
        self.unpackInterface.set_gui_config(cfg)
        print("=== 已注入配置到解包页面 ===")
        logger.info("已注入配置到解包页面")

        # 配置变更时重新加载数据
        si.game_path_changed.connect(lambda: self._reload_unpack_data(cfg))
        si.output_path_changed.connect(lambda: self._reload_unpack_data(cfg))

        # 首页初始化完成后加载数据
        print("=== 准备加载初始数据 ===")
        logger.info("准备加载初始数据")
        hi.loading_label.setText("正在加载实体数据…")
        self._load_initial_data(cfg)
        print("=== _load_initial_data 已调用 ===")

    def _load_initial_data(self, cfg):
        """程序启动时加载实体数据"""
        from lol_audio_unpack.app_context import create_app_context
        from lol_audio_unpack.gui.service.worker import DataLoadWorker
        from loguru import logger

        print("=== _load_initial_data 开始执行 ===")
        logger.info("开始加载初始数据")

        try:
            cli_overrides = {
                "source_mode": cfg.source_mode,
                "game_path": cfg.game_path,
                "output_path": cfg.output_path,
                "game_region": cfg.game_region,
                "group_by_type": cfg.group_by_type,
                "remote_live_region": cfg.remote_live_region,
                "cleanup_remote": cfg.cleanup_remote,
                "snapshot_version": cfg.snapshot_version,
                "snapshot_lcu_url": cfg.snapshot_lcu_url,
                "snapshot_game_url": cfg.snapshot_game_url,
            }
            print(f"=== 配置: output_path={cfg.output_path}, game_path={cfg.game_path} ===")
            app_context = create_app_context(cli_overrides=cli_overrides)
            print("=== AppContext 创建成功 ===")
            logger.info(f"AppContext 创建成功: output_path={cfg.output_path}")
        except Exception as e:
            print(f"=== 创建 AppContext 失败: {e} ===")
            logger.error(f"创建 AppContext 失败: {e}")
            self.homeInterface.loading_label.setText("数据加载失败")
            self.homeInterface.progress_bar.stop()
            return

        print("=== 启动 champions 数据加载 Worker ===")
        logger.info("启动 champions 数据加载")
        self._champions_worker = DataLoadWorker(app_context, "champions")
        self._champions_worker.finished.connect(lambda data: self._on_champions_loaded(data, cfg))
        self._champions_worker.error.connect(self._on_data_load_error)
        self._champions_worker.start()
        print("=== Champions Worker 已启动 ===")

    def _on_champions_loaded(self, data, cfg):
        """Champions 数据加载完成"""
        from loguru import logger

        print(f"=== _on_champions_loaded 被调用，数据量: {len(data)} ===")
        logger.info(f"Champions 数据加载完成，共 {len(data)} 条")

        self.unpackInterface._cached_data["champions"] = data
        print(f"=== Champions 数据已存入缓存 ===")

        # 继续加载 maps 数据
        from lol_audio_unpack.app_context import create_app_context
        from lol_audio_unpack.gui.service.worker import DataLoadWorker

        try:
            cli_overrides = {
                "source_mode": cfg.source_mode,
                "game_path": cfg.game_path,
                "output_path": cfg.output_path,
                "game_region": cfg.game_region,
                "group_by_type": cfg.group_by_type,
                "remote_live_region": cfg.remote_live_region,
                "cleanup_remote": cfg.cleanup_remote,
                "snapshot_version": cfg.snapshot_version,
                "snapshot_lcu_url": cfg.snapshot_lcu_url,
                "snapshot_game_url": cfg.snapshot_game_url,
            }
            app_context = create_app_context(cli_overrides=cli_overrides)
        except Exception as e:
            logger.error(f"创建 AppContext 失败: {e}")
            self._finish_data_loading()
            return

        logger.info("启动 maps 数据加载")
        self._maps_worker = DataLoadWorker(app_context, "maps")
        self._maps_worker.finished.connect(lambda data: self._on_maps_loaded(data))
        self._maps_worker.error.connect(self._on_data_load_error)
        self._maps_worker.start()

    def _on_maps_loaded(self, data):
        """Maps 数据加载完成"""
        from loguru import logger
        logger.info(f"Maps 数据加载完成，共 {len(data)} 条")

        self.unpackInterface._cached_data["maps"] = data
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
        self.homeInterface.loading_label.setText(f"加载失败: {error}")
        self.homeInterface.progress_bar.stop()

    def _finish_data_loading(self):
        """完成数据加载"""
        self.homeInterface.loading_label.setText("数据加载完成")
        self.homeInterface.progress_bar.stop()
        self.homeInterface._loading_widget.setVisible(False)

    def _reload_unpack_data(self, cfg):
        """配置变更时重新加载数据"""
        self.unpackInterface._cached_data = {"champions": [], "maps": []}
        self.homeInterface.loading_label.setText("正在重新加载数据…")
        self.homeInterface.progress_bar.start()
        self.homeInterface._loading_widget.setVisible(True)
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
