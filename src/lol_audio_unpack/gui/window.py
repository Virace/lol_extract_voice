"""主窗口与全局日志面板布局逻辑。"""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

from loguru import logger
from PySide6.QtCore import (
    QEvent,
    QRect,
    QSize,
    Qt,
)
from PySide6.QtGui import QIcon, QResizeEvent
from PySide6.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    CaptionLabel,
    CardWidget,
    FluentWindow,
    InfoBar,
    InfoBarPosition,
    NavigationItemPosition,
    PlainTextEdit,
    SplashScreen,
    StrongBodyLabel,
    Theme,
    TransparentToolButton,
    isDarkTheme,
    qconfig,
    setTheme,
    setThemeColor,
)
from qfluentwidgets import (
    FluentIcon as FIF,
)

from lol_audio_unpack import __version__
from lol_audio_unpack.app_context import create_app_context
from lol_audio_unpack.gui.common import apply_smooth_scroll_enabled
from lol_audio_unpack.gui.service.worker import DataLoadWorker
from lol_audio_unpack.gui.view.about_page import AboutPage
from lol_audio_unpack.gui.view.execution_page import ExecutionPage
from lol_audio_unpack.gui.view.home_page import HomePage
from lol_audio_unpack.gui.view.overview_page import OverviewPage
from lol_audio_unpack.gui.view.setting_page import SettingPage
from lol_audio_unpack.utils.logging import setup_logging

NAV_EXPANDED_WIDTH_THRESHOLD = 100
LOG_PANEL_MIN_HEIGHT = 248
LOG_PANEL_MAX_HEIGHT = 360
LOG_PANEL_COLLAPSED_HEIGHT = 58
LOG_PANEL_SIDE_MARGIN = 24
LOG_PANEL_BOTTOM_MARGIN = 16
LOG_PANEL_TOP_MARGIN = 16


def _build_log_panel_host_rect(window_size: QSize, navigation_width: int) -> QRect:
    """根据主窗口尺寸与导航宽度推导页面内容区矩形。

    Args:
        window_size: 主窗口当前尺寸。
        navigation_width: 当前导航栏占用宽度。

    Returns:
        近似代表页面内容区的宿主矩形。
    """
    x = max(0, navigation_width)
    width = max(0, window_size.width() - x)
    return QRect(x, 0, width, window_size.height())


def _build_log_panel_geometry(host_rect: QRect, expanded: bool) -> QRect:
    """根据页面内容区计算全局日志面板的位置与大小。

    Args:
        host_rect: 页面内容区矩形。
        expanded: 面板是否处于展开状态。

    Returns:
        日志面板对应的目标矩形区域。
    """
    width = max(0, host_rect.width() - LOG_PANEL_SIDE_MARGIN * 2)
    expanded_height = min(max(int(host_rect.height() * 0.34), LOG_PANEL_MIN_HEIGHT), LOG_PANEL_MAX_HEIGHT)
    height = expanded_height if expanded else LOG_PANEL_COLLAPSED_HEIGHT
    x = host_rect.x() + LOG_PANEL_SIDE_MARGIN
    max_y = host_rect.y() + host_rect.height() - LOG_PANEL_BOTTOM_MARGIN - height
    y = max(host_rect.y() + LOG_PANEL_TOP_MARGIN, max_y)
    return QRect(x, y, width, height)


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
        self.addSubInterface(self.homeInterface, FIF.HOME, '主页')
        self.addSubInterface(self.overviewInterface, FIF.DOCUMENT, '实体总览')
        self.addSubInterface(self.executionInterface, FIF.DOWNLOAD, '执行中心')
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
        """设置主窗口尺寸、标题与基础事件过滤器。"""
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

    def _init_global_log_panel(self) -> None:
        """初始化主窗口底部的全局日志面板。"""
        self._log_panel_expanded = True

        self._log_panel_card = CardWidget(self)
        self._log_panel_card.setObjectName("GlobalLogPanel")
        panel_layout = QVBoxLayout(self._log_panel_card)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        self._log_panel_header = QWidget(self._log_panel_card)
        self._log_panel_header.setObjectName("GlobalLogPanelHeader")
        header_layout = QHBoxLayout(self._log_panel_header)
        header_layout.setContentsMargins(20, 16, 20, 12)
        header_layout.setSpacing(12)

        title_layout = QVBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(2)
        self._log_panel_title = StrongBodyLabel("日志详情", self._log_panel_header)
        self._log_panel_subtitle = CaptionLabel("执行中心日志会实时同步到这里。", self._log_panel_header)
        self._log_panel_subtitle.setObjectName("GlobalLogPanelSubtitle")
        title_layout.addWidget(self._log_panel_title)
        title_layout.addWidget(self._log_panel_subtitle)
        header_layout.addLayout(title_layout, 1)

        self._log_panel_toggle_btn = TransparentToolButton(FIF.UP, self._log_panel_header)
        self._log_panel_toggle_btn.setToolTip("收起日志详情")
        self._log_panel_toggle_btn.clicked.connect(self._toggle_log_panel)
        header_layout.addWidget(self._log_panel_toggle_btn, 0, Qt.AlignTop)

        self._log_panel_body = QWidget(self._log_panel_card)
        self._log_panel_body.setObjectName("GlobalLogPanelBody")
        body_layout = QVBoxLayout(self._log_panel_body)
        body_layout.setContentsMargins(20, 0, 20, 20)
        body_layout.setSpacing(0)
        self._global_log_output = PlainTextEdit(self._log_panel_body)
        self._global_log_output.setReadOnly(True)
        body_layout.addWidget(self._global_log_output, 1)

        panel_layout.addWidget(self._log_panel_header, 0)
        panel_layout.addWidget(self._log_panel_body, 1)

        qconfig.themeChanged.connect(lambda _theme: self._refresh_log_panel_surface_style())
        qconfig.themeColorChanged.connect(lambda _color: self._refresh_log_panel_surface_style())

        self._set_global_log_text(self.executionInterface.current_log_text())
        self._refresh_log_panel_surface_style()
        self._set_log_panel_expanded(True)

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
            logger.info(f"日志系统已重定向到输出目录: {log_dir}")

        # 路径改变时实时同步到首页
        si.game_path_changed.connect(hi.update_game_dir)
        si.output_path_changed.connect(hi.update_output_dir)
        si.wwiser_path_changed.connect(hi.update_wwiser)
        si.vgmstream_path_changed.connect(hi.update_vgmstream)

        # 注入配置到各业务页面
        self.executionInterface.set_gui_config(cfg)
        self.overviewInterface.set_gui_config(cfg)
        self.overviewInterface.selection_sync_requested.connect(self.executionInterface.set_selected_entities)
        self.executionInterface.refresh_requested.connect(self._refresh_shared_output_data)
        self.executionInterface.task_running_changed.connect(self._on_unpack_task_running_changed)
        self.executionInterface.log_text_changed.connect(self._set_global_log_text)
        self.settingInterface.smooth_scroll_changed.connect(self._apply_smooth_scroll_setting)
        self._apply_smooth_scroll_setting(
            cfg.page_smooth_scroll_enabled,
            cfg.widget_smooth_scroll_enabled,
        )

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

    def _set_global_log_text(self, text: str) -> None:
        """同步执行中心日志全文到主窗口级日志面板。"""
        self._global_log_output.setPlainText(text)
        self._global_log_output.verticalScrollBar().setValue(self._global_log_output.verticalScrollBar().maximum())

    def _current_log_panel_host_rect(self) -> QRect:
        """返回当前主窗口中可用于日志面板的页面内容区。"""
        return _build_log_panel_host_rect(self.size(), self.navigationInterface.width())

    def _update_log_panel_toggle_button(self, expanded: bool) -> None:
        """刷新日志面板切换按钮的图标与提示文案。"""
        self._log_panel_toggle_btn.setIcon(FIF.UP if expanded else FIF.DOWN)
        self._log_panel_toggle_btn.setToolTip("收起日志详情" if expanded else "展开日志详情")

    def _refresh_log_panel_surface_style(self) -> None:
        """按当前主题刷新日志面板外壳与标题条样式。"""
        if isDarkTheme():
            card_border = "rgba(255, 255, 255, 41)"
            card_background = "rgb(28, 31, 38)"
            header_border = "rgba(255, 255, 255, 46)"
            header_background = "rgb(28, 31, 38)"
            title_color = "rgb(245, 245, 245)"
            subtitle_color = "rgba(245, 245, 245, 0.72)"
            editor_background = "rgb(28, 31, 38)"
            editor_border = "rgba(255, 255, 255, 28)"
        else:
            card_border = "rgba(0, 0, 0, 26)"
            card_background = "rgb(255, 255, 255)"
            header_border = "rgba(0, 0, 0, 26)"
            header_background = "rgb(255, 255, 255)"
            title_color = "rgb(28, 28, 28)"
            subtitle_color = "rgba(28, 28, 28, 0.64)"
            editor_background = "rgb(255, 255, 255)"
            editor_border = "rgba(0, 0, 0, 20)"
        self._log_panel_card.setStyleSheet(
            f"""
            CardWidget#GlobalLogPanel {{
                background-color: {card_background};
                border: 1px solid {card_border};
                border-radius: 16px;
            }}
            QWidget#GlobalLogPanelHeader {{
                background-color: {header_background};
                border-top-left-radius: 16px;
                border-top-right-radius: 16px;
                border-bottom: 1px solid {header_border};
            }}
            QWidget#GlobalLogPanelBody {{
                background-color: {card_background};
                border-bottom-left-radius: 16px;
                border-bottom-right-radius: 16px;
            }}
            CaptionLabel#GlobalLogPanelSubtitle {{
                color: {subtitle_color};
                background-color: transparent;
                border: none;
                padding: 0;
            }}
            """
        )
        self._log_panel_title.setStyleSheet(
            f"""
            StrongBodyLabel {{
                border: none;
                background-color: transparent;
                color: {title_color};
                padding: 0;
            }}
            """
        )
        self._global_log_output.setStyleSheet(
            f"""
            PlainTextEdit {{
                background-color: {editor_background};
                border: 1px solid {editor_border};
                border-radius: 12px;
            }}
            """
        )

    def _toggle_log_panel(self) -> None:
        """切换全局日志面板的展开状态。"""
        self._set_log_panel_expanded(not self._log_panel_expanded)

    def _set_log_panel_expanded(self, expanded: bool) -> None:
        """设置全局日志面板的展开状态。"""
        self._log_panel_expanded = expanded
        self._log_panel_subtitle.setVisible(expanded)
        self._log_panel_body.setVisible(expanded)
        self._update_log_panel_toggle_button(expanded)
        self._log_panel_card.setGeometry(
            _build_log_panel_geometry(self._current_log_panel_host_rect(), expanded)
        )
        self._log_panel_card.raise_()

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
        apply_smooth_scroll_enabled(self._global_log_output, widget_enabled)

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
        if not hasattr(self, "_log_panel_card"):
            return
        self._set_log_panel_expanded(self._log_panel_expanded)
