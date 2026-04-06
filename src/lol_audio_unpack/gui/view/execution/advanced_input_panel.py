"""执行中心的高级输入面板。"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget
from qfluentwidgets import CheckBox, ComboBox, LineEdit, SegmentedWidget
from qfluentwidgets import FluentIcon as FIF

from lol_audio_unpack.gui.components.accordion_setting_card import FormAccordionCard


class AdvancedInputPanel(FormAccordionCard):
    """承载执行中心的高级输入控件。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化高级输入折叠卡。

        Args:
            parent: 父级控件。
        """
        super().__init__(
            FIF.SETTING,
            "自定义输入",
            "需要精细调整时，可以在这里补充范围和任务选项。",
            parent,
        )
        self.setExpand(True)

        self.champion_ids_input = LineEdit()
        self.champion_ids_input.setPlaceholderText("英雄 ID，如 1,103,555")
        self.champion_ids_input.setMinimumWidth(260)
        self.champion_ids_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.champion_ids_input.setClearButtonEnabled(True)

        self.map_ids_input = LineEdit()
        self.map_ids_input.setPlaceholderText("地图 ID，如 0,11,12")
        self.map_ids_input.setMinimumWidth(260)
        self.map_ids_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.map_ids_input.setClearButtonEnabled(True)

        self.vo_filter = SegmentedWidget()
        self.vo_filter.addItem("VO", "仅 VO")
        self.vo_filter.addItem("ALL", "全部类型")
        self.vo_filter.setCurrentItem("VO")
        self.vo_filter.setMinimumWidth(220)
        self.vo_filter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.max_workers_combo = ComboBox()
        self.max_workers_combo.addItems(["1", "2", "4", "8", "16", "32", "64"])
        self.max_workers_combo.setCurrentText("4")
        self.max_workers_combo.setMinimumWidth(120)
        self.max_workers_combo.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)

        self.bp_voice_cb = CheckBox("启用")
        self.bp_voice_cb.setChecked(True)
        self.force_update_cb = CheckBox("启用")
        self.integrate_data_cb = CheckBox("启用")
        self.wav_task_cb = CheckBox("启用")
        self.wav_format_combo = ComboBox()
        self.wav_format_combo.addItems(["auto", "pcm16", "pcm24", "pcm32", "float"])
        self.wav_format_combo.setCurrentText("pcm16")
        self.wav_format_combo.setMinimumWidth(120)
        self.wav_format_combo.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        self.wav_format_combo.setVisible(True)

        self.wav_format_row = QWidget(self)
        self.wav_format_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        wav_format_layout = QHBoxLayout(self.wav_format_row)
        wav_format_layout.setContentsMargins(0, 0, 0, 0)
        wav_format_layout.setSpacing(8)
        wav_format_layout.addWidget(self.wav_format_combo)
        wav_format_layout.addStretch(1)

        self.add_form_row("英雄 ID", "多个英雄 ID 用逗号分隔，如 1,103,555", self.champion_ids_input)
        self.add_form_row("地图 ID", "多个地图 ID 用逗号分隔，如 0,11,12", self.map_ids_input)
        self.add_form_row("音频范围", "默认只处理 VO，需要时可切换为全部类型", self.vo_filter)
        self.add_form_row("并发数", "设置任务并发数；一般不建议超过 CPU 线程数", self.max_workers_combo)
        self.add_form_row("附加 BP 语音", "默认同时处理 BP 语音", self.bp_voice_cb)
        self.add_form_row("转码格式", "仅在启用音频转码时生效", self.wav_format_row)
        self.add_form_row(
            "前置强制更新",
            "在执行解包或映射前先强制刷新基础数据，相当于先跑一次 update --force",
            self.force_update_cb,
        )
        self.add_form_row(
            "整合数据文件",
            "映射任务时额外生成整合数据，便于后续整理和查看",
            self.integrate_data_cb,
        )
        self.set_wav_control_state(wav_enabled=False)

    def set_wav_control_state(self, *, wav_enabled: bool) -> None:
        """同步音频转码格式控件状态。"""
        self.wav_format_combo.setVisible(True)
        self.wav_format_combo.setEnabled(wav_enabled)
