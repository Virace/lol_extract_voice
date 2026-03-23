from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout

from qfluentwidgets import (
    SmoothScrollArea,
    TitleLabel,
    BodyLabel,
    CardWidget,
    SubtitleLabel,
    IconWidget,
    TransparentToolButton,
    FluentIcon as FIF
)

from lol_audio_unpack import __version__


class AboutPage(SmoothScrollArea):
    """
    About page containing project info, versions, and links.
    """
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("AboutPage")
        self.view = QWidget(self)
        self.view.setObjectName("AboutPageView")
        self.view.setStyleSheet("QWidget#AboutPageView{background: transparent}")
        self.setWidget(self.view)
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea {border: none; background: transparent;}")

        self._build_ui()

    def _build_ui(self):
        root_layout = QVBoxLayout(self.view)
        root_layout.setContentsMargins(36, 36, 36, 36)
        root_layout.setSpacing(24)

        # Title
        title_label = TitleLabel("关于 Lol Audio Unpack", self)
        root_layout.addWidget(title_label)

        # Info Card
        info_card = CardWidget(self)
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(20, 20, 20, 20)
        info_layout.setSpacing(12)

        info_layout.addWidget(SubtitleLabel("工具信息", info_card))
        info_layout.addWidget(BodyLabel(f"当前版本: {__version__}", info_card))
        info_layout.addWidget(BodyLabel("作者: Virace", info_card))
        info_layout.addWidget(BodyLabel("基于 Python 和 PySide6 + QFluentWidgets 构建。", info_card))
        
        root_layout.addWidget(info_card)

        # Links Card
        link_card = CardWidget(self)
        link_layout = QVBoxLayout(link_card)
        link_layout.setContentsMargins(20, 20, 20, 20)
        link_layout.setSpacing(12)

        link_layout.addWidget(SubtitleLabel("相关链接", link_card))

        github_layout = QHBoxLayout()
        github_icon = IconWidget(FIF.GITHUB, link_card)
        github_icon.setFixedSize(16, 16)
        github_label = BodyLabel("GitHub 源码仓库", link_card)
        
        github_btn = TransparentToolButton(FIF.LINK, link_card)
        github_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/Virace/lol_extract_voice")))
        
        github_layout.addWidget(github_icon)
        github_layout.addWidget(github_label)
        github_layout.addStretch(1)
        github_layout.addWidget(github_btn)

        link_layout.addLayout(github_layout)
        
        root_layout.addWidget(link_card)
        root_layout.addStretch(1)
