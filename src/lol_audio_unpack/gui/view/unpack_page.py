from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action,
    CheckBox,
    DropDownPushButton,
    InfoBar,
    InfoBarPosition,
    PrimaryPushButton,
    ProgressBar,
    RoundMenu,
    SearchLineEdit,
    SegmentedWidget,
    SmoothScrollArea,
    SubtitleLabel,
    TableWidget,
)

if TYPE_CHECKING:
    from lol_audio_unpack.app_context import AppContext

from lol_audio_unpack.app_context import create_app_context
from lol_audio_unpack.gui.service.worker import DataLoadWorker


class UnpackPage(QWidget):
    """
    Main Unpack Page with Table layout of heroes.
    """
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("UnpackPage")
        self.setStyleSheet("QWidget#UnpackPage{background: transparent}")
        self.gui_config = None
        self._cached_data = {"champions": [], "maps": []}
        self._worker = None
        self._build_ui()
        self._setup_connections()

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 24, 24, 24)
        root_layout.setSpacing(16)

        # 头部标题
        title_label = SubtitleLabel("音频解包", self)
        root_layout.addWidget(title_label)

        # 顶部视图切换
        self.nav_pivot = SegmentedWidget(self)
        self.nav_pivot.addItem("champions", "英雄")
        self.nav_pivot.addItem("maps", "地图")
        self.nav_pivot.setCurrentItem("champions")

        root_layout.addWidget(self.nav_pivot)

        # 顶部操作区 (搜索, 筛选)
        top_bar = QHBoxLayout()
        self.search_input = SearchLineEdit(self)
        self.search_input.setPlaceholderText("搜索英雄 (支持中英)")
        self.search_input.setFixedWidth(240)

        # 使用 SegmentedWidget 模拟 LiteFilter 效果 (原版 LiteFilter 为 Pro 组件)
        self.vo_filter = SegmentedWidget(self)
        self.vo_filter.addItem("VO", "VO")
        self.vo_filter.addItem("ALL", "ALL")

        self.vo_filter.setCurrentItem("VO")

        top_bar.addWidget(self.search_input)
        top_bar.addStretch(1)
        top_bar.addWidget(self.vo_filter)


        root_layout.addLayout(top_bar)

        # 中间内容区（实体表格）
        self.hero_table = TableWidget(self)
        self.hero_table.setBorderVisible(True)
        self.hero_table.setBorderRadius(8)
        self.hero_table.setWordWrap(False)
        self.hero_table.setColumnCount(4)
        self.hero_table.setHorizontalHeaderLabels(["ID", "实体", "音频", "映射"])
        self.hero_table.verticalHeader().hide()
        self.hero_table.setAlternatingRowColors(True)
        # 支持多选以配合右键菜单的"解包选中"
        self.hero_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.hero_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.hero_table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        # 表头拉伸
        self.hero_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.hero_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.hero_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.hero_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.hero_table.setColumnWidth(2, 85)
        self.hero_table.setColumnWidth(3, 85)

        # 添加右键菜单支持
        self.hero_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.hero_table.customContextMenuRequested.connect(self._show_context_menu)

        root_layout.addWidget(self.hero_table, 1)

        # 底部操作栏
        bottom_bar_frame = QFrame(self)
        bottom_bar_frame.setObjectName("BottomBar")
        bottom_bar_frame.setStyleSheet("""
            QFrame#BottomBar {
                background-color: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
            }
        """)
        bottom_layout = QVBoxLayout(bottom_bar_frame)

        actions_row = QHBoxLayout()
        self.bp_voice_cb = CheckBox("附加 BP 语音", self)
        self.bp_voice_cb.setChecked(True)
        # 全部解包是主操作；解包选中通过右键菜单触发
        self.unpack_all_btn = PrimaryPushButton("全部解包", self)

        actions_row.addWidget(self.bp_voice_cb)
        actions_row.addStretch(1)
        actions_row.addWidget(self.unpack_all_btn)

        bottom_layout.addLayout(actions_row)

        self.progress_bar = ProgressBar(self)
        self.progress_bar.setVisible(False)
        bottom_layout.addWidget(self.progress_bar)

        root_layout.addWidget(bottom_bar_frame)

    def _setup_connections(self):
        """设置信号连接"""
        self.nav_pivot.currentItemChanged.connect(self._on_nav_changed)
        self.search_input.textChanged.connect(self._on_search_text_changed)

    def showEvent(self, event):
        """页面显示时展示已加载的数据"""
        super().showEvent(event)
        current_key = self.nav_pivot.currentRouteKey()
        logger.info(f"UnpackPage showEvent 触发，current_key={current_key}")
        logger.info(f"缓存数据: champions={len(self._cached_data.get('champions', []))}, maps={len(self._cached_data.get('maps', []))}")

        if current_key:
            if self._cached_data.get(current_key):
                logger.info(f"显示 {current_key} 数据，共 {len(self._cached_data[current_key])} 条")
                self.add_preview_data(self._cached_data[current_key])
            else:
                logger.warning(f"没有可显示的数据: current_key={current_key}，尝试加载...")
                if self.gui_config:
                    self.load_data(current_key)

    def set_gui_config(self, cfg):
        """注入 GUI 配置"""
        self.gui_config = cfg

    def _create_app_context(self):
        """从 GUI 配置创建 AppContext（用于数据读取）"""
        cli_overrides = {
            "source_mode": self.gui_config.source_mode,
            "game_path": self.gui_config.game_path,
            "output_path": self.gui_config.output_path,
            "game_region": self.gui_config.game_region,
            "group_by_type": self.gui_config.group_by_type,
            "remote_live_region": self.gui_config.remote_live_region,
            "cleanup_remote": self.gui_config.cleanup_remote,
            "snapshot_version": self.gui_config.snapshot_version,
            "snapshot_lcu_url": self.gui_config.snapshot_lcu_url,
            "snapshot_game_url": self.gui_config.snapshot_game_url,
        }
        return create_app_context(cli_overrides=cli_overrides)

    def load_data(self, entity_type: str, force_reload: bool = False):
        """异步加载实体数据（避免 200+ 实体阻塞 UI）"""
        if not self.gui_config:
            return

        # 使用缓存避免重复加载
        if not force_reload and self._cached_data[entity_type]:
            self.add_preview_data(self._cached_data[entity_type])
            return

        # 防止重复启动加载任务
        if self._worker and self._worker.isRunning():
            return

        try:
            app_context = self._create_app_context()
        except Exception as e:
            InfoBar.error("初始化失败", str(e), parent=self, position=InfoBarPosition.TOP)
            return

        # 启动后台线程加载数据
        self.progress_bar.setVisible(True)
        self._worker = DataLoadWorker(app_context, entity_type)
        self._worker.finished.connect(lambda data: self._on_data_loaded(entity_type, data))
        self._worker.error.connect(self._on_load_error)
        self._worker.start()

    def _on_data_loaded(self, entity_type: str, data: list):
        """数据加载完成"""
        self.progress_bar.setVisible(False)
        self._cached_data[entity_type] = data
        self.add_preview_data(data)

    def _on_load_error(self, error: str):
        """数据加载失败"""
        self.progress_bar.setVisible(False)
        InfoBar.error("加载失败", error, parent=self, position=InfoBarPosition.TOP)

    def _on_nav_changed(self, key: str):
        """导航切换"""
        self.load_data(key)

    def _on_search_text_changed(self, text: str):
        """搜索过滤：支持中文名称和英文 alias"""
        text = text.lower().strip()
        # 获取当前标签页类型（champions 或 maps）
        current_type = self.nav_pivot.currentRouteKey()
        cached = self._cached_data.get(current_type, [])

        # 遍历表格行，根据名称或 alias 匹配来显示/隐藏
        for row in range(self.hero_table.rowCount()):
            name_item = self.hero_table.item(row, 1)
            if not name_item:
                continue

            entity_id = self.hero_table.item(row, 0).text()
            alias = next((d["alias"] for d in cached if d["id"] == entity_id), "")

            name_match = text in name_item.text().lower()
            alias_match = text in alias.lower()

            self.hero_table.setRowHidden(row, not (name_match or alias_match))

    def add_preview_data(self, data_list):
        """Temporary helper to populate preview data into the table."""
        self.hero_table.setRowCount(len(data_list))
        for row_idx, data in enumerate(data_list):
            id_item = QTableWidgetItem(data["id"])
            name_item = QTableWidgetItem(data["name"])
            audio_item = QTableWidgetItem(data["audio"])
            mapping_item = QTableWidgetItem(data.get("mapping", "未存在"))

            # 文本居中
            id_item.setTextAlignment(Qt.AlignCenter)
            audio_item.setTextAlignment(Qt.AlignCenter)
            mapping_item.setTextAlignment(Qt.AlignCenter)

            # 音频列颜色
            if data["audio"] == "已存在":
                audio_item.setForeground(QColor(0, 200, 0))
            else:
                audio_item.setForeground(QColor(255, 165, 0))

            # 映射列颜色
            if data.get("mapping") == "已存在":
                mapping_item.setForeground(QColor(0, 200, 0))
            else:
                mapping_item.setForeground(QColor(255, 165, 0))

            self.hero_table.setItem(row_idx, 0, id_item)
            self.hero_table.setItem(row_idx, 1, name_item)
            self.hero_table.setItem(row_idx, 2, audio_item)
            self.hero_table.setItem(row_idx, 3, mapping_item)

            self.hero_table.setRowHeight(row_idx, 36)

    def _show_context_menu(self, pos):
        """Show custom right-click context menu."""
        # 只有选中行时才展示菜单
        if not self.hero_table.selectedItems():
            return
        menu = RoundMenu(parent=self)
        unpack_selected_action = Action("解包选中", triggered=lambda: print("Unpack Selected"))
        menu.addAction(unpack_selected_action)
        menu.exec(self.hero_table.mapToGlobal(pos))
