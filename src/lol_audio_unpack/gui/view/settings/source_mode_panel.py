"""设置页的数据来源面板。"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import PushSettingCard, SettingCardGroup

from lol_audio_unpack.gui.view.settings.cards import ComboRowSettingCard
from lol_audio_unpack.gui.view.settings.remote_source_panel import RemoteSourcePanel


class SourceModePanel:
    """承载来源模式、本地目录与远端来源区域。"""

    def __init__(self, *, parent: QWidget, source_mode_map: dict[str, str]) -> None:
        """初始化来源模式面板。"""
        self.sourceModeGroup = SettingCardGroup("数据来源", parent)
        self.sourceModeCard = ComboRowSettingCard(
            FIF.CLOUD,
            "来源模式",
            "本地模式使用已安装的游戏目录；远程模式根据所提供的信息自动下载所需文件",
            list(source_mode_map.keys()),
            label_map=source_mode_map,
        )
        self.sourceModeGroup.addSettingCard(self.sourceModeCard)

        self.localGroup = SettingCardGroup("本地目录", parent)
        self.gamePathCard = PushSettingCard(
            "选择文件夹",
            FIF.FOLDER,
            "游戏根目录",
            "当前: 未设置",
        )
        self.localGroup.addSettingCard(self.gamePathCard)

        self.remoteSourcePanel = RemoteSourcePanel(parent)

    def add_to_layout(self, layout) -> None:
        """把来源相关分组依次加入外层布局。"""
        layout.addWidget(self.sourceModeGroup)
        layout.addWidget(self.localGroup)
        layout.addWidget(self.remoteSourcePanel.group)
