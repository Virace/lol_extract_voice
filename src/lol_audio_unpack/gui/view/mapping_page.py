from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QSplitter
)

from qfluentwidgets import (
    ListWidget,
    SubtitleLabel,
    BodyLabel,
    TextEdit,
    PrimaryPushButton,
    PushButton,
    SearchLineEdit
)


class MappingPage(QWidget):
    """
    Mapping viewer page with two-pane layout: list on left, text preview on right.
    """
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("MappingPage")
        self.setStyleSheet("QWidget#MappingPage{background: transparent}")
        self._build_ui()

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 24, 24, 24)
        root_layout.setSpacing(16)

        # 头部标题
        header_layout = QHBoxLayout()
        title_label = SubtitleLabel("资源映射", self)
        refresh_btn = PrimaryPushButton("刷新数据", self)
        
        header_layout.addWidget(title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(refresh_btn)
        root_layout.addLayout(header_layout)
        
        # 主体: Splitter        # 左右分割容器
        self.splitter = QSplitter(Qt.Horizontal, self)
        self.splitter.setObjectName("MappingSplitter")
        self.splitter.setStyleSheet("""
            QSplitter#MappingSplitter::handle {
                background-color: rgba(255, 255, 255, 0.08);
                margin: 4px 2px;
                border-radius: 2px;
                width: 4px;
            }
            QSplitter#MappingSplitter::handle:hover {
                background-color: rgba(255, 255, 255, 0.15);
            }
            QSplitter#MappingSplitter::handle:pressed {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """)
        
        # 左侧面板 (英雄列表)
        left_widget = QWidget(self.splitter)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 6, 0)  # 给右侧分割线留一点空隙
        
        search_input = SearchLineEdit(left_widget)
        search_input.setPlaceholderText("搜英雄...")
        left_layout.addWidget(search_input)
        
        self.hero_list = ListWidget(left_widget)
        self.hero_list.setAlternatingRowColors(True)
        
        # Dummy Items for preview
        self.hero_list.addItems([
            "Ahri (阿狸)",
            "Aatrox (亚托克斯)",
            "Annie (安妮)",
            "Jinx (金克丝)",
            "Yone (永恩)",
            "Yuumi (悠米)"
        ])
        
        left_layout.addWidget(BodyLabel("已提取映射表 (Mapping)", left_widget))
        left_layout.addWidget(self.hero_list, 1)

        # 右侧面板 (Mapping 预览)
        right_widget = QWidget(self.splitter)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(6, 0, 0, 0) # 减小间隔
        right_layout.setSpacing(8)
        
        right_header = QHBoxLayout()
        self.preview_title = SubtitleLabel("选中项预览", right_widget)
        self.open_dir_btn = PushButton("打开所在目录", right_widget)
        
        right_header.addWidget(self.preview_title)
        right_header.addStretch(1)
        right_header.addWidget(self.open_dir_btn)
        right_layout.addLayout(right_header)
        
        self.text_preview = TextEdit(right_widget)
        self.text_preview.setReadOnly(True)
        self.text_preview.setPlainText("{\n  \"entityType\": \"champion\",\n  \"entityName\": \"Ahri\"\n}")
        right_layout.addWidget(self.text_preview)
        
        self.splitter.addWidget(left_widget)
        self.splitter.addWidget(right_widget)
        self.splitter.setSizes([300, 700])
        
        root_layout.addWidget(self.splitter, 1)
