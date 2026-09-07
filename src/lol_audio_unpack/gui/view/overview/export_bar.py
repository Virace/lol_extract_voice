"""总览音频选择模式的上下文工具与底部导出栏。"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, CheckBox, FluentIcon, PrimaryPushButton, ProgressBar, PushButton, ToolButton


class AudioExportBar(QWidget):
    """提供右侧单行选择工具和底部 WAV 导出入口。

    ``context_bar`` 与 ``footer_bar`` 由音频预览面板分别放在列表的上方和下方，
    因而选择工具不会挤占列表高度，底部导出入口也不会变成列表上方的通栏按钮。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """创建选择工具、模式入口和底部导出按钮。

        Args:
            parent: 音频预览面板。
        """
        super().__init__(parent)
        self.active = False
        self._index_loading = False
        self.hide()
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

        self.context_bar = QWidget(parent)
        self.context_bar.setObjectName("OverviewAudioContextBar")
        self.context_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.context_bar.setMinimumHeight(32)
        context_layout = QHBoxLayout(self.context_bar)
        context_layout.setContentsMargins(0, 0, 0, 0)
        context_layout.setSpacing(6)
        self.context_layout = context_layout

        self.summary = CaptionLabel("", self.context_bar)
        self.summary_label = self.summary
        self.summary.setWordWrap(False)
        self.summary.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        context_layout.addWidget(self.summary, 1)

        self.progress_bar = ProgressBar(self.context_bar, useAni=False)
        self.progress_bar.setAccessibleName("全部音频加载进度")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedWidth(96)
        self.progress_bar.hide()
        context_layout.addWidget(self.progress_bar)

        self.tools = QWidget(self.context_bar)
        self.tools.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        tools_layout = QHBoxLayout(self.tools)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        tools_layout.setSpacing(6)
        self.all_button = PushButton("全选", self.tools)
        self.all_button.setToolTip("全选当前实体目录中的可用文件，不受搜索条件影响")
        self.clear_button = PushButton("清空", self.tools)
        self.clear_button.setToolTip("取消当前实体的全部音频选择，不删除文件")
        self.undo_button = ToolButton(FluentIcon.RETURN, self.tools)
        self.undo_button.setAccessibleName("撤销选择")
        self.undo_button.setToolTip("撤销上一次选择修改")
        self.only_selected = CheckBox("仅看已选", self.tools)
        for widget in (self.all_button, self.clear_button, self.undo_button, self.only_selected):
            tools_layout.addWidget(widget)
        context_layout.addWidget(self.tools)
        context_layout.addStretch(1)

        self.mode_button = PushButton("选择导出", self.context_bar)
        self.mode_button.setAccessibleName("音频选择模式")
        self.mode_button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        context_layout.addWidget(self.mode_button)

        self.footer_bar = QWidget(parent)
        self.footer_bar.setObjectName("OverviewAudioExportFooter")
        self.footer_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        footer_layout = QVBoxLayout(self.footer_bar)
        footer_layout.setContentsMargins(0, 8, 0, 0)
        footer_layout.setSpacing(8)

        self.separator = QFrame(self.footer_bar)
        self.separator.setFrameShape(QFrame.Shape.HLine)
        self.separator.setFrameShadow(QFrame.Shadow.Plain)
        self.separator.setFixedHeight(1)
        footer_layout.addWidget(self.separator)

        footer_row = QHBoxLayout()
        footer_row.setContentsMargins(0, 0, 0, 0)
        footer_row.setSpacing(8)
        self.selection_count = CaptionLabel("", self.footer_bar)
        self.selection_count.setWordWrap(False)
        self.selection_count.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        footer_row.addWidget(self.selection_count, 1)
        self.export_button = PrimaryPushButton("导出 WAV…", self.footer_bar)
        self.export_button.setToolTip("核对当前选择并导出 WAV")
        footer_row.addWidget(self.export_button)
        footer_layout.addLayout(footer_row)

        self.tools.hide()
        self.mode_button.setEnabled(False)

    def set_mode(self, active: bool) -> None:
        """切换选择工具的可见性并保持单行布局。

        Args:
            active: 是否进入显式音频选择模式。
        """
        self.active = active
        self.tools.setVisible(active)
        self.summary.setVisible(not active)
        self.progress_bar.setVisible(self._index_loading and not active)
        self.mode_button.setText("退出选择" if active else "选择导出")

    def set_load_progress(self, current: int, total: int) -> None:
        """浏览时展示索引进度，选择时由底部文本反馈，避免挤压工具。"""
        self._index_loading = True
        maximum = max(int(total), 1)
        self.progress_bar.setRange(0, maximum)
        self.progress_bar.setValue(max(0, min(int(current), maximum)))
        self.progress_bar.setVisible(not self.active)

    def clear_load_progress(self) -> None:
        """隐藏并重置索引进度。"""
        self._index_loading = False
        self.progress_bar.hide()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)

    def set_export_visible(self, visible: bool) -> None:
        """在原始数据模式隐藏音频选择工具与导出入口。

        Args:
            visible: 是否显示上下文工具和底部导出栏。
        """
        self.context_bar.setVisible(visible)
        self.footer_bar.setVisible(visible)
