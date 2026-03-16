from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout

from qfluentwidgets import (
    SmoothScrollArea,
    TitleLabel,
    BodyLabel,
    CardWidget,
    SubtitleLabel,
    ProgressBar,
    FlowLayout,
    IconWidget,
    CaptionLabel
)
from qfluentwidgets import FluentIcon as FIF


class ElidedLabel(CaptionLabel):
    """A label that elides text when it overflows the layout."""
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full_text = text
        self.setMinimumWidth(50)

    def setText(self, text):
        self._full_text = text
        self._elide_text()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide_text()

    def _elide_text(self):
        metrics = self.fontMetrics()
        elided = metrics.elidedText(self._full_text, Qt.TextElideMode.ElideRight, self.width() - 2)
        super().setText(elided)


class ClickableCard(CardWidget):
    """Custom card widget with click event signal."""
    clicked = Signal()

    def __init__(self, icon, title, content, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(240, 140)
        
        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(20, 20, 20, 20)
        self.vBoxLayout.setSpacing(4)
        
        # Header (Icon on left, Link Icon on right)
        self.headerLayout = QHBoxLayout()
        self.headerLayout.setContentsMargins(0, 0, 0, 0)
        
        self.iconWidget = IconWidget(icon, self)
        self.iconWidget.setFixedSize(24, 24)
        
        self.linkIcon = IconWidget(FIF.LINK, self)
        self.linkIcon.setFixedSize(14, 14)
        
        self.headerLayout.addWidget(self.iconWidget)
        self.headerLayout.addStretch(1)
        self.headerLayout.addWidget(self.linkIcon)
        self.headerLayout.setAlignment(self.linkIcon, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        
        # Labels
        self.titleLabel = SubtitleLabel(title, self)
        
        self.contentLabel = ElidedLabel(content, self)
        self.contentLabel.setTextColor(Qt.GlobalColor.gray, Qt.GlobalColor.gray)
        self.contentLabel.setToolTip(content)  # Full content on hover
        
        self.vBoxLayout.addLayout(self.headerLayout)
        self.vBoxLayout.addSpacing(12)
        self.vBoxLayout.addWidget(self.titleLabel)
        self.vBoxLayout.addSpacing(4)
        self.vBoxLayout.addWidget(self.contentLabel)
        self.vBoxLayout.addStretch(1)
        
    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        self.clicked.emit()


class HomePage(SmoothScrollArea):
    """
    Home page for the application overview and client status.
    """
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("HomePage")
        self.view = QWidget(self)
        self.view.setObjectName("HomePageView")
        self.view.setStyleSheet("QWidget#HomePageView{background: transparent}")
        self.setWidget(self.view)
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea {border: none; background: transparent;}")

        self._build_ui()

    def _build_ui(self):
        root_layout = QVBoxLayout(self.view)
        root_layout.setContentsMargins(36, 36, 36, 36)
        root_layout.setSpacing(24)

        # Title Section
        self.title_label = TitleLabel("欢迎使用 Lol Audio Unpack", self)
        root_layout.addWidget(self.title_label)
        
        desc = BodyLabel(
            "该工具用于提取《英雄联盟》客户端中的原始音频资源，输出 `.wem` 文件，这包含了英雄与地图相关的可用资源。", 
            self
        )
        desc.setWordWrap(True)
        root_layout.addWidget(desc)

        # Loading Section
        loading_layout = QVBoxLayout()
        loading_layout.setSpacing(8)
        self.loading_label = BodyLabel("正在加载数据...", self)
        self.progress_bar = ProgressBar(self)
        self.progress_bar.setValue(30)
        loading_layout.addWidget(self.loading_label)
        loading_layout.addWidget(self.progress_bar)
        root_layout.addLayout(loading_layout)

        # Dashboard / Cards Section
        self.flow_layout = FlowLayout()
        self.flow_layout.setContentsMargins(0, 0, 0, 0)
        self.flow_layout.setHorizontalSpacing(16)
        self.flow_layout.setVerticalSpacing(16)
        
        # Cards definitions: icon, title, content, handler
        cards_data = [
            (FIF.CODE, "游戏版本", "16.5", self.on_game_version_clicked),
            (FIF.FOLDER, "游戏目录", r"D:\Games\Tencent\WeGameApps\英雄联盟\Game", self.on_game_dir_clicked),
            (FIF.DOWNLOAD, "输出目录", r".\output", self.on_output_dir_clicked),
            (FIF.DEVELOPER_TOOLS, "wwiser", r".\tools\wwiser\wwiser.pyz", self.on_wwiser_clicked),
            (FIF.COMMAND_PROMPT, "vgmstream-cli", r".\tools\vgmstream\vgmstream-cli.exe", self.on_vgmstream_clicked),
        ]

        self.cards = []
        for icon, title, content, handler in cards_data:
            card = ClickableCard(icon, title, content, self)
            card.clicked.connect(handler)
            self.cards.append(card)
            self.flow_layout.addWidget(card)

        # 保存输出目录卡片引用以便后续更新
        self.output_dir_card = self.cards[2]
            
        root_layout.addLayout(self.flow_layout)
        root_layout.addStretch(1)

    # Click Event Handlers (TODO implementations)
    def on_game_version_clicked(self):
        print("TODO: Open game version json file")

    def on_game_dir_clicked(self):
        print("TODO: Open game directory")

    def on_output_dir_clicked(self):
        print("TODO: Open output directory")

    def on_wwiser_clicked(self):
        print("TODO: Open wwiser directory")

    def on_vgmstream_clicked(self):
        print("TODO: Open vgmstream-cli directory")

    def update_dir_status(self, has_dir: bool, version: str | None = None):
        """Method to update UI state based on backend. (Legacy compatibility)"""
        pass

    def update_output_dir(self, path: str) -> None:
        """更新输出目录卡片显示。"""
        display_path = path if path else r".\output"
        self.output_dir_card.contentLabel.setText(display_path)
        self.output_dir_card.contentLabel.setToolTip(display_path)
