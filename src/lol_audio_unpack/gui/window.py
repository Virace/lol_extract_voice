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

        # create sub interface
        self.homeInterface = HomePage(self)
        self.unpackInterface = UnpackPage(self)
        self.mappingInterface = MappingPage(self)
        self.settingInterface = SettingPage(self)
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

        self._inject_mock_data()
        
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
        """连接页面间的数据同步。"""
        # 初始化时从设置同步输出目录到首页
        output_path = self.settingInterface.config.output_path
        self.homeInterface.update_output_dir(output_path)

        # 设置改变时同步到首页
        self.settingInterface.output_path_changed.connect(
            self.homeInterface.update_output_dir
        )

    def _inject_mock_data(self):
        self.unpackInterface.add_preview_data([
            {"id": "1", "name": "Annie", "status": "ready", "types": ["VO", "SFX"]},
            {"id": "103", "name": "Ahri", "status": "cached", "types": ["VO", "SFX", "MUSIC"]},
            {"id": "222", "name": "Jinx", "status": "ready", "types": ["VO", "SFX"]},
            {"id": "266", "name": "Aatrox", "status": "staged", "types": ["VO", "SFX", "MUSIC"]},
            {"id": "350", "name": "Yuumi", "status": "missing", "types": ["VO"]},
            {"id": "777", "name": "Yone", "status": "ready", "types": ["VO", "SFX"]},
            {"id": "0", "name": "Common Map", "status": "queued", "types": ["SFX"]},
            {"id": "11", "name": "SR Map", "status": "cached", "types": ["VO", "SFX", "MUSIC"]},
        ])
