"""设置页的基础设置与工具路径面板。"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import PushSettingCard, SettingCardGroup

from lol_audio_unpack.gui.view.settings.cards import (
    ComboRowSettingCard,
    LocalizedSwitchSettingCard,
)


class BaseSettingsPanel:
    """承载输出目录、游戏区域与分组设置。"""

    def __init__(self, *, parent: QWidget) -> None:
        self.group = SettingCardGroup("基础设置", parent)
        self.outputPathCard = PushSettingCard(
            "选择文件夹",
            FIF.FOLDER,
            "解包输出目录",
            "当前: 未设置",
        )
        self.gameRegionCard = ComboRowSettingCard(
            FIF.LANGUAGE,
            "游戏区域",
            "语音文件的区域标识，影响实际加载的语音资源",
            ["zh_CN", "en_US", "ja_JP", "ko_KR", "fr_FR", "de_DE", "es_ES", "pt_BR", "ru_RU"],
        )
        self.groupByTypeCard = LocalizedSwitchSettingCard(
            FIF.FOLDER,
            "按类型分组输出",
            "开: audios/类型/英雄/…   关(默认): audios/英雄/类型/…",
        )

        self.group.addSettingCard(self.outputPathCard)
        self.group.addSettingCard(self.gameRegionCard)
        self.group.addSettingCard(self.groupByTypeCard)


class ToolPathPanel:
    """承载外部工具路径设置。"""

    def __init__(self, *, parent: QWidget) -> None:
        self.group = SettingCardGroup("工具配置", parent)
        self.wwiserCard = PushSettingCard(
            "选择文件",
            FIF.DEVELOPER_TOOLS,
            "wwiser 路径",
            "Mapping 功能依赖此工具 (wwiser.py)  —  https://github.com/bnnm/wwiser",
        )
        self.vgmstreamCard = PushSettingCard(
            "选择文件",
            FIF.COMMAND_PROMPT,
            "vgmstream-cli 路径",
            "音频转码依赖此工具 (vgmstream-cli.exe)  —  解包 .wem → .wav 格式",
        )

        self.group.addSettingCard(self.wwiserCard)
        self.group.addSettingCard(self.vgmstreamCard)
