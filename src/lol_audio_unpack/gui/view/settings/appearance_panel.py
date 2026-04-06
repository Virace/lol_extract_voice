"""设置页的个性化面板。"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from PySide6.QtWidgets import QWidget
from qfluentwidgets import (
    FluentIcon as FIF,
)
from qfluentwidgets import (
    FluentIconBase,
    OptionsSettingCard,
    SettingCardGroup,
    Theme,
    qconfig,
)

from lol_audio_unpack.gui.theme import list_accent_presets
from lol_audio_unpack.gui.view.settings.cards import (
    ComboRowSettingCard,
    LocalizedSwitchSettingCard,
    LogLevelSettingCard,
    SliderSettingCard,
    SmoothScrollSettingCard,
)

ICON_ASSET_DIR = Path(__file__).resolve().parents[2] / "assets" / "icon"


class AccentPresetIcon(FluentIconBase, Enum):
    """固定强调色预设使用的自定义 Fluent 图标。"""

    DOT = "circle-solid-full.svg"

    def path(self, theme=Theme.AUTO) -> str:
        """返回图标资源路径。"""
        _ = theme
        return str(ICON_ASSET_DIR / self.value)


class AppearancePanel:
    """承载设置页的主题、滚动、试听与日志偏好。"""

    def __init__(
        self,
        *,
        parent: QWidget,
        audio_output_device_options: list[tuple[str, str]],
    ) -> None:
        accent_presets = list_accent_presets()
        self.group = SettingCardGroup("个性化", parent)

        self.themeCard = OptionsSettingCard(
            qconfig.themeMode,
            FIF.BRUSH,
            "应用主题",
            "设置界面的明暗模式",
            texts=["浅色", "深色", "跟随系统"],
            parent=self.group,
        )
        self.accentPresetCard = ComboRowSettingCard(
            FIF.PALETTE,
            "主题颜色",
            "选择应用的固定强调色预设。",
            [preset.label for preset in accent_presets],
            label_map={preset.label: preset.id for preset in accent_presets},
            parent=self.group,
        )
        for index, preset in enumerate(accent_presets):
            self.accentPresetCard.comboBox.setItemIcon(
                index,
                AccentPresetIcon.DOT.icon(color=preset.primary_color),
            )

        self.group.addSettingCard(self.themeCard)
        self.group.addSettingCard(self.accentPresetCard)
        self.smoothScrollCard = SmoothScrollSettingCard(self.group)
        self.group.addSettingCard(self.smoothScrollCard)

        self.previewAudioOutputDeviceCard = ComboRowSettingCard(
            FIF.MUSIC,
            "播放设备",
            "默认跟随系统当前输出设备；如有多路输出，可在此固定指定试听设备。",
            [label for label, _value in audio_output_device_options],
            label_map={label: value for label, value in audio_output_device_options},
            parent=self.group,
        )
        self.group.addSettingCard(self.previewAudioOutputDeviceCard)

        self.previewAudioVolumeCard = SliderSettingCard(
            FIF.VOLUME,
            "试听音量",
            "控制显式音频 ID 叶子行的本地试听音量。",
            minimum=0,
            maximum=100,
            value=10,
            parent=self.group,
        )
        self.group.addSettingCard(self.previewAudioVolumeCard)

        self.logDrawerAutoCollapseCard = LocalizedSwitchSettingCard(
            FIF.SETTING,
            "点击外部自动收起日志",
            "开启后日志抽屉展开时会显示全局蒙版，并在点击内容区其他位置时自动收起。",
            parent=self.group,
        )
        self.logLevelCard = LogLevelSettingCard(self.group)
        self.consoleLogLevelCard = self.logLevelCard.consoleLevelCard
        self.fileLogLevelCard = self.logLevelCard.fileLevelCard
        self.group.addSettingCard(self.logDrawerAutoCollapseCard)
        self.group.addSettingCard(self.logLevelCard)
