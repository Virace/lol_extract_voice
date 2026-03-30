"""实体总览右侧资源预览壳层。"""

from __future__ import annotations

from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import QHBoxLayout, QPlainTextEdit, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import (
    CaptionLabel,
    LineEdit,
    PlainTextEdit,
    SegmentedWidget,
    StrongBodyLabel,
    TransparentToolButton,
)
from qfluentwidgets import (
    FluentIcon as FIF,
)

from lol_audio_unpack.gui.view.overview.audio_preview_panel import OverviewAudioPreviewPanel


def create_preview_path_edit(parent: QWidget | None = None) -> LineEdit:
    """创建跟随 Fluent 主题的预览路径输入框。"""
    line_edit = LineEdit(parent)
    line_edit.setReadOnly(True)
    line_edit.setClearButtonEnabled(False)
    line_edit.setPlaceholderText("请选择左侧实体以查看原始数据。")
    line_edit.setMinimumWidth(0)
    return line_edit


class OverviewPreviewPanel(QWidget):
    """承载总览页右侧资源预览壳层。"""

    def __init__(self, *, audio_summary_placeholder: str, parent: QWidget | None = None) -> None:
        """初始化右侧资源预览面板。

        Args:
            audio_summary_placeholder: 事件树摘要默认文案。
            parent: 父级控件。
        """
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(8)

        preview_title = StrongBodyLabel("资源预览", self)
        preview_hint = CaptionLabel("右侧可以查看当前实体的事件和原始数据。", self)
        preview_hint.setWordWrap(True)
        layout.addWidget(preview_title)
        layout.addWidget(preview_hint)

        header_layout = QHBoxLayout()
        self.preview_path_edit = create_preview_path_edit(self)
        self.reveal_file_btn = TransparentToolButton(FIF.LINK, self)
        self.reveal_file_btn.setToolTip("打开文件所在位置")
        self.reveal_file_btn.setFixedSize(32, 32)
        self.reveal_file_btn.setEnabled(False)
        header_layout.addWidget(self.preview_path_edit, 1)
        header_layout.addWidget(self.reveal_file_btn)
        layout.addLayout(header_layout)

        self.preview_mode_pivot = SegmentedWidget(self)
        self.preview_mode_pivot.addItem("audio", "事件")
        self.preview_mode_pivot.addItem("raw", "原始数据")
        self.preview_mode_pivot.setCurrentItem("audio")
        layout.addWidget(self.preview_mode_pivot)

        self.preview_stack = QStackedWidget(self)
        self.text_preview = PlainTextEdit(self)
        self.text_preview.setReadOnly(True)
        self.text_preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.text_preview.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        self.text_preview.setCenterOnScroll(False)
        self.text_preview.setUndoRedoEnabled(False)
        self.text_preview.verticalScrollBar().setSingleStep(18)
        self.text_preview.horizontalScrollBar().setSingleStep(18)
        self.text_preview.setPlainText("请选择左侧实体以查看原始数据。")
        self.preview_stack.addWidget(self.text_preview)

        self.audio_preview_panel = OverviewAudioPreviewPanel(
            summary_placeholder=audio_summary_placeholder,
            parent=self,
        )
        self.preview_stack.addWidget(self.audio_preview_panel)
        self.preview_stack.setCurrentWidget(self.audio_preview_panel)
        self.audio_preview_panel.set_summary_visible(True)
        layout.addWidget(self.preview_stack, 1)

    def set_audio_mode(self, is_audio_mode: bool) -> None:
        """切换当前显示的预览模式。

        Args:
            is_audio_mode: 为 ``True`` 时显示事件树，否则显示原始文本。
        """
        self.preview_stack.setCurrentWidget(self.audio_preview_panel if is_audio_mode else self.text_preview)
        self.audio_preview_panel.set_summary_visible(is_audio_mode)

    def set_preview_path(self, text: str) -> None:
        """同步右上角映射路径显示。

        Args:
            text: 预览路径文本。
        """
        self.preview_path_edit.setText(text)
        self.preview_path_edit.setToolTip(text)

    def show_placeholder(self, message: str) -> None:
        """显示空态提示并清理路径展示。

        Args:
            message: 要展示的占位提示。
        """
        self.preview_path_edit.clear()
        self.preview_path_edit.setToolTip("")
        self.text_preview.setPlainText(message)
        self.audio_preview_panel.clear_preview()
        self.reveal_file_btn.setEnabled(False)
        self.set_audio_mode(False)
