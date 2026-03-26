"""关于页面展示品牌信息、版本信息与相关链接。"""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    IconWidget,
    SmoothScrollArea,
    SubtitleLabel,
    TitleLabel,
    TransparentToolButton,
)
from qfluentwidgets import (
    FluentIcon as FIF,
)

from lol_audio_unpack import __version__
from lol_audio_unpack.gui.common.icon import get_app_logo_path


class AboutPage(SmoothScrollArea):
    """展示项目品牌信息、版本信息与外部链接。"""

    def __init__(self, parent=None):
        """初始化关于页面。

        Args:
            parent: 父级窗口或容器。
        """
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
        """构建关于页面的布局内容。"""
        root_layout = QVBoxLayout(self.view)
        root_layout.setContentsMargins(36, 36, 36, 36)
        root_layout.setSpacing(24)

        # Title
        title_label = TitleLabel("关于 Lol Audio Unpack", self)
        root_layout.addWidget(title_label)

        # Hero Card
        hero_card = CardWidget(self)
        hero_layout = QVBoxLayout(hero_card)
        hero_layout.setContentsMargins(28, 28, 28, 28)
        hero_layout.setSpacing(10)
        hero_layout.setAlignment(Qt.AlignHCenter)

        logo_path = get_app_logo_path()
        if logo_path is not None:
            logo_widget = QSvgWidget(str(logo_path), hero_card)
            logo_widget.setObjectName("AboutPageLogo")
            logo_widget.setFixedSize(144, 144)
            hero_layout.addWidget(logo_widget, alignment=Qt.AlignHCenter)

        hero_title = SubtitleLabel("Lol Audio Unpack", hero_card)
        hero_title.setAlignment(Qt.AlignHCenter)
        hero_layout.addWidget(hero_title)

        hero_description = BodyLabel("英雄联盟音频提取与事件映射工具", hero_card)
        hero_description.setAlignment(Qt.AlignHCenter)
        hero_description.setWordWrap(True)
        hero_layout.addWidget(hero_description)

        hero_version = BodyLabel(f"当前版本: {__version__}", hero_card)
        hero_version.setAlignment(Qt.AlignHCenter)
        hero_layout.addWidget(hero_version)

        root_layout.addWidget(hero_card)

        # Info Card
        info_card = CardWidget(self)
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(20, 20, 20, 20)
        info_layout.setSpacing(12)

        info_layout.addWidget(SubtitleLabel("工具信息", info_card))
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
        github_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/Virace/lol_audio_unpack")))

        github_layout.addWidget(github_icon)
        github_layout.addWidget(github_label)
        github_layout.addStretch(1)
        github_layout.addWidget(github_btn)

        link_layout.addLayout(github_layout)

        root_layout.addWidget(link_card)
        root_layout.addStretch(1)
