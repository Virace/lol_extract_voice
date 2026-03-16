from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
)

from qfluentwidgets import (
    SearchLineEdit,
    CheckBox,
    PrimaryPushButton,
    ProgressBar,
    SubtitleLabel,
    TableWidget,
    SmoothScrollArea,
    SegmentedWidget,
    DropDownPushButton,
    RoundMenu,
    Action
)


class UnpackPage(QWidget):
    """
    Main Unpack Page with Table layout of heroes.
    """
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("UnpackPage")
        self.setStyleSheet("QWidget#UnpackPage{background: transparent}")
        self._build_ui()

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

        # 中间内容区（英雄表格）
        self.hero_table = TableWidget(self)
        self.hero_table.setBorderVisible(True)
        self.hero_table.setBorderRadius(8)
        self.hero_table.setWordWrap(False)
        self.hero_table.setColumnCount(3)
        self.hero_table.setHorizontalHeaderLabels(["ID", "英雄", "状态"])
        self.hero_table.verticalHeader().hide()
        self.hero_table.setAlternatingRowColors(True)
        # 支持多选以配合右键菜单的“解包选中”
        self.hero_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.hero_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.hero_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        # 表头拉伸
        self.hero_table.horizontalHeader().setStretchLastSection(True)
        self.hero_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.hero_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.hero_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        
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
        
    def add_preview_data(self, data_list):
        """Temporary helper to populate preview data into the table."""
        self.hero_table.setRowCount(len(data_list))
        for row_idx, data in enumerate(data_list):
            id_item = QTableWidgetItem(data["id"])
            name_item = QTableWidgetItem(data["name"])
            status_item = QTableWidgetItem(data["status"])
            
            # 文本居中
            id_item.setTextAlignment(Qt.AlignCenter)
            status_item.setTextAlignment(Qt.AlignCenter)

            self.hero_table.setItem(row_idx, 0, id_item)
            self.hero_table.setItem(row_idx, 1, name_item)
            self.hero_table.setItem(row_idx, 2, status_item)
            
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
