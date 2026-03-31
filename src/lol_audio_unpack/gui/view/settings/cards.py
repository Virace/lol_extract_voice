"""设置页可复用的 Fluent 设置卡组件。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
from qfluentwidgets import (
    BodyLabel,
    ComboBox,
    IndicatorPosition,
    LineEdit,
    SettingCard,
    Slider,
    SwitchButton,
    SwitchSettingCard,
    qconfig,
)
from qfluentwidgets import (
    FluentIcon as FIF,
)

from lol_audio_unpack.gui.common.font_compat import apply_switch_button_safe_font
from lol_audio_unpack.gui.components.accordion_setting_card import FormAccordionCard


class ComboRowSettingCard(SettingCard):
    """右侧带下拉框的设置卡。"""

    def __init__(  # noqa: PLR0913
        self,
        icon,
        title: str,
        content: str,
        items: list[str],
        label_map: dict[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """初始化下拉框设置卡。

        Args:
            icon: Fluent 图标。
            title: 标题文案。
            content: 说明文案。
            items: 下拉框显示项。
            label_map: 显示文案到实际值的映射。
            parent: 父级控件。
        """
        super().__init__(icon, title, content, parent)
        self._label_map = label_map or {}
        self.comboBox = ComboBox(self)
        self.comboBox.addItems(items)
        self.hBoxLayout.addWidget(self.comboBox, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def value(self) -> str:
        """返回当前选项对应的实际值。"""
        label = self.comboBox.currentText()
        return self._label_map.get(label, label)

    def setValue(self, text: str) -> None:
        """按实际值或显示文字定位选项。"""
        reverse = {value: key for key, value in self._label_map.items()}
        label = reverse.get(text, text)
        idx = self.comboBox.findText(label)
        if idx >= 0:
            self.comboBox.setCurrentIndex(idx)

    def displayValue(self) -> str:
        """返回当前下拉框显示文案。"""
        return self.comboBox.currentText()


class ComboRowBinding:
    """为独立 `ComboBox` 提供与设置卡一致的值接口。"""

    def __init__(self, combo_box: ComboBox, label_map: dict[str, str] | None = None) -> None:
        """初始化组合框值绑定。

        Args:
            combo_box: 目标下拉框。
            label_map: 显示文案到实际值的映射。
        """
        self.comboBox = combo_box
        self._label_map = label_map or {}

    def value(self) -> str:
        """返回当前选项对应的实际值。"""
        label = self.comboBox.currentText()
        return self._label_map.get(label, label)

    def setValue(self, text: str) -> None:
        """按实际值或显示文字定位选项。"""
        reverse = {value: key for key, value in self._label_map.items()}
        label = reverse.get(text, text)
        idx = self.comboBox.findText(label)
        if idx >= 0:
            self.comboBox.setCurrentIndex(idx)


class LineEditSettingCard(SettingCard):
    """右侧带输入框的设置卡。"""

    def __init__(
        self,
        icon,
        title: str,
        content: str,
        placeholder: str = "",
        parent: QWidget | None = None,
    ) -> None:
        """初始化输入框设置卡。

        Args:
            icon: Fluent 图标。
            title: 标题文案。
            content: 说明文案。
            placeholder: 输入框占位文案。
            parent: 父级控件。
        """
        super().__init__(icon, title, content, parent)
        self.lineEdit = LineEdit(self)
        self.lineEdit.setPlaceholderText(placeholder)
        self.lineEdit.setFixedWidth(320)
        self.lineEdit.setClearButtonEnabled(True)
        self.hBoxLayout.addWidget(self.lineEdit, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def value(self) -> str:
        """返回去掉首尾空白后的输入值。"""
        return self.lineEdit.text().strip()

    def setValue(self, text: str) -> None:
        """同步输入框文本。"""
        self.lineEdit.setText(text)


class SliderSettingCard(SettingCard):
    """右侧带滑块和百分比文案的设置卡。"""

    def __init__(  # noqa: PLR0913
        self,
        icon,
        title: str,
        content: str,
        *,
        minimum: int,
        maximum: int,
        value: int,
        parent: QWidget | None = None,
    ) -> None:
        """初始化滑块设置卡。

        Args:
            icon: Fluent 图标。
            title: 标题文案。
            content: 说明文案。
            minimum: 最小值。
            maximum: 最大值。
            value: 初始值。
            parent: 父级控件。
        """
        super().__init__(icon, title, content, parent)
        self.slider = Slider(Qt.Orientation.Horizontal, self)
        self.slider.setRange(minimum, maximum)
        self.slider.setFixedWidth(180)
        self.valueLabel = BodyLabel(self)
        self.valueLabel.setMinimumWidth(44)
        self.valueLabel.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.slider.valueChanged.connect(self._sync_value_label)
        self.hBoxLayout.addWidget(self.slider, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(12)
        self.hBoxLayout.addWidget(self.valueLabel, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self.setValue(value)

    def value(self) -> int:
        """返回当前滑块值。"""
        return int(self.slider.value())

    def setValue(self, value: int) -> None:
        """同步滑块值并刷新右侧百分比。"""
        normalized = int(value)
        self.slider.setValue(normalized)
        self._sync_value_label(normalized)

    def _sync_value_label(self, value: int) -> None:
        """同步右侧百分比文案。"""
        self.valueLabel.setText(f"{int(value)}%")


class LocalizedSwitchSettingCard(SwitchSettingCard):
    """使用中文开关文案的设置卡。"""

    def __init__(
        self,
        icon,
        title: str,
        content: str | None = None,
        configItem=None,
        parent: QWidget | None = None,
    ) -> None:
        """初始化开关设置卡。

        Args:
            icon: Fluent 图标。
            title: 标题文案。
            content: 说明文案。
            configItem: 绑定的 qconfig 项。
            parent: 父级控件。
        """
        self._on_text = "开"
        self._off_text = "关"
        super().__init__(icon, title, content, configItem=configItem, parent=parent)
        apply_switch_button_safe_font(self.switchButton)
        self._sync_switch_text(self.isChecked())

    def _sync_switch_text(self, is_checked: bool) -> None:
        """同步右侧开关按钮文案。"""
        self.switchButton.setOnText(self._on_text)
        self.switchButton.setOffText(self._off_text)
        self.switchButton.setText(self._on_text if is_checked else self._off_text)

    def setValue(self, isChecked: bool) -> None:
        """设置当前勾选状态并保持中文文案。"""
        if self.configItem:
            qconfig.set(self.configItem, isChecked)

        self.switchButton.setChecked(isChecked)
        self._sync_switch_text(isChecked)


class FixedSnapshotCard(FormAccordionCard):
    """固定快照三元组输入卡。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化固定快照配置组。

        Args:
            parent: 父级控件。
        """
        super().__init__(
            FIF.PIN,
            "固定快照（高阶）",
            "锁定指定版本的远端快照；三项必须同时填写，留空则自动获取最新",
            parent,
        )
        self.versionEdit = LineEdit()
        self.versionEdit.setPlaceholderText("例: 15.5.1")
        self.versionEdit.setFixedWidth(240)
        self.versionEdit.setClearButtonEnabled(True)

        self.lcuUrlEdit = LineEdit()
        self.lcuUrlEdit.setPlaceholderText("https://...")
        self.lcuUrlEdit.setFixedWidth(360)
        self.lcuUrlEdit.setClearButtonEnabled(True)

        self.gameUrlEdit = LineEdit()
        self.gameUrlEdit.setPlaceholderText("https://...")
        self.gameUrlEdit.setFixedWidth(360)
        self.gameUrlEdit.setClearButtonEnabled(True)

        self.add_form_row("版本号", "REMOTE_VERSION", self.versionEdit)
        self.add_form_row("LCU Manifest URL", "REMOTE_LCU_MANIFEST_URL", self.lcuUrlEdit)
        self.add_form_row("Game Manifest URL", "REMOTE_GAME_MANIFEST_URL", self.gameUrlEdit)

    def versionValue(self) -> str:
        """返回版本号输入值。"""
        return self.versionEdit.text().strip()

    def lcuUrlValue(self) -> str:
        """返回 LCU Manifest URL 输入值。"""
        return self.lcuUrlEdit.text().strip()

    def gameUrlValue(self) -> str:
        """返回 Game Manifest URL 输入值。"""
        return self.gameUrlEdit.text().strip()

    def isComplete(self) -> bool:
        """返回固定快照三元组是否已完整填写。"""
        return bool(self.versionValue() and self.lcuUrlValue() and self.gameUrlValue())

    def setValues(self, version: str, lcu_url: str, game_url: str) -> None:
        """同步固定快照三元组。"""
        self.versionEdit.setText(version)
        self.lcuUrlEdit.setText(lcu_url)
        self.gameUrlEdit.setText(game_url)


class SmoothScrollSettingCard(FormAccordionCard):
    """可折叠的平滑滚动配置组。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化平滑滚动设置卡。

        Args:
            parent: 父级控件。
        """
        super().__init__(
            FIF.SCROLL,
            "平滑滚动",
            "数据量过多时开启平滑滚动可能会卡顿；页面滚动和列表/表格等控件可分别控制。",
            parent,
        )
        self.pageSwitchButton = self._add_switch_row(
            "页面级滚动",
            "设置页、主页、关于页、执行中心等页面容器的滚动动画。",
        )
        self.widgetSwitchButton = self._add_switch_row(
            "控件级滚动",
            "列表、表格、日志区、文本预览等可滚动控件的滚动动画。",
        )

    def _add_switch_row(self, title: str, content: str) -> SwitchButton:
        """添加一行带中文开关按钮的说明项。"""
        switch_button = SwitchButton("关", self, IndicatorPosition.RIGHT)
        switch_button.setOnText("开")
        switch_button.setOffText("关")
        switch_button.setText("关")
        apply_switch_button_safe_font(switch_button)
        self.add_form_row(title, content, switch_button)
        return switch_button

    def pageScrollEnabled(self) -> bool:
        """返回是否启用页面级平滑滚动。"""
        return self.pageSwitchButton.isChecked()

    def widgetScrollEnabled(self) -> bool:
        """返回是否启用控件级平滑滚动。"""
        return self.widgetSwitchButton.isChecked()

    def setValues(self, *, page_enabled: bool, widget_enabled: bool) -> None:
        """同步两项平滑滚动开关状态。"""
        self.pageSwitchButton.setChecked(page_enabled)
        self.widgetSwitchButton.setChecked(widget_enabled)


class LogLevelSettingCard(FormAccordionCard):
    """可折叠的日志等级配置组。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化日志等级设置卡。

        Args:
            parent: 父级控件。
        """
        super().__init__(
            FIF.INFO,
            "日志等级",
            "分别控制控制台/窗口与文件日志的详细程度；高频控制台日志可能影响窗口流畅度。",
            parent,
        )
        items = ["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR"]
        self.consoleLevelCard = self._add_combo_row(
            "控制台与窗口日志等级",
            "影响 shell 输出和窗口内全局日志面板的展示级别。",
            items,
        )
        self.fileLevelCard = self._add_combo_row(
            "文件日志等级",
            "影响输出目录 logs 下文件日志的详细程度。",
            items,
        )

    def _add_combo_row(
        self,
        title: str,
        content: str,
        items: list[str],
        label_map: dict[str, str] | None = None,
    ) -> ComboRowBinding:
        """添加一行带下拉框的日志等级设置项。"""
        combo_box = ComboBox(self)
        combo_box.addItems(items)
        combo_box.setFixedWidth(180)
        self.add_form_row(title, content, combo_box)
        return ComboRowBinding(combo_box, label_map)

    def consoleValue(self) -> str:
        """返回当前控制台日志等级。"""
        return self.consoleLevelCard.value()

    def fileValue(self) -> str:
        """返回当前文件日志等级。"""
        return self.fileLevelCard.value()

    def setValues(self, *, console_level: str, file_level: str) -> None:
        """同步两项日志等级。"""
        self.consoleLevelCard.setValue(console_level)
        self.fileLevelCard.setValue(file_level)
