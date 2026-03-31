"""设置页的个性化面板。"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget
from qfluentwidgets import (
    CustomColorSettingCard,
    OptionsSettingCard,
    SettingCardGroup,
    qconfig,
)
from qfluentwidgets import (
    FluentIcon as FIF,
)

from lol_audio_unpack.gui.view.settings.cards import (
    ComboRowSettingCard,
    LocalizedSwitchSettingCard,
    LogLevelSettingCard,
    SliderSettingCard,
    SmoothScrollSettingCard,
)


class AppearancePanel:
    """承载设置页的主题、滚动、试听与日志偏好。"""

    def __init__(
        self,
        *,
        parent: QWidget,
        audio_output_device_options: list[tuple[str, str]],
    ) -> None:
        self.group = SettingCardGroup("个性化", parent)

        self.themeCard = OptionsSettingCard(
            qconfig.themeMode,
            FIF.BRUSH,
            "应用主题",
            "设置界面的明暗模式",
            texts=["浅色", "深色", "跟随系统"],
            parent=self.group,
        )
        self.colorCard = CustomColorSettingCard(
            qconfig.themeColor,
            FIF.PALETTE,
            "主题颜色",
            "自定义应用的强调色",
            self.group,
        )
        self.colorCard.defaultRadioButton.setText("默认颜色")
        self.colorCard.customRadioButton.setText("自定义颜色")
        self.colorCard.customLabel.setText("自定义颜色")
        self.colorCard.chooseColorButton.setText("选择颜色")
        self.colorCard.choiceLabel.setText(self.colorCard.buttonGroup.checkedButton().text())
        self.colorCard.choiceLabel.adjustSize()

        self.group.addSettingCard(self.themeCard)
        self.group.addSettingCard(self.colorCard)
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
