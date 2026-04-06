"""实体总览右侧资源预览壳层。"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QKeySequence, QPalette, QTextOption
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPlainTextEdit, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import (
    Action,
    BodyLabel,
    LineEdit,
    MenuAnimationType,
    RoundMenu,
    SearchLineEdit,
    SegmentedWidget,
    Theme,
    TransparentToolButton,
    qconfig,
)
from qfluentwidgets import (
    FluentIcon as FIF,
)

from lol_audio_unpack.gui.common.font_compat import apply_line_edit_safe_font, apply_tool_button_safe_font
from lol_audio_unpack.gui.common.styles import get_fluent_frame_stroke_pair, get_fluent_text_primary_pair
from lol_audio_unpack.gui.view.overview.audio_preview_panel import OverviewAudioPreviewPanel

DEFAULT_PREVIEW_PLACEHOLDER_TEXT = "请选择左侧实体。"


def build_raw_preview_theme_pair() -> tuple[str, str]:
    """构造 raw 文本预览的亮暗主题样式。"""
    light_border, dark_border = get_fluent_frame_stroke_pair()
    light_text, dark_text = get_fluent_text_primary_pair()
    light_qss = f"""
    QPlainTextEdit {{
        background: transparent;
        background-color: transparent;
        color: {light_text};
        border: 1px solid {light_border};
        border-radius: 10px;
        padding: 8px 10px;
        outline: none;
    }}
    QPlainTextEdit:focus {{
        border: 1px solid {light_border};
        outline: none;
    }}
    """
    dark_qss = f"""
    QPlainTextEdit {{
        background: transparent;
        background-color: transparent;
        color: {dark_text};
        border: 1px solid {dark_border};
        border-radius: 10px;
        padding: 8px 10px;
        outline: none;
    }}
    QPlainTextEdit:focus {{
        border: 1px solid {dark_border};
        outline: none;
    }}
    """
    return light_qss, dark_qss


def create_preview_path_edit(parent: QWidget | None = None) -> LineEdit:
    """创建跟随 Fluent 主题的预览路径输入框。"""
    line_edit = LineEdit(parent)
    line_edit.setReadOnly(True)
    line_edit.setClearButtonEnabled(False)
    line_edit.setPlaceholderText(DEFAULT_PREVIEW_PLACEHOLDER_TEXT)
    line_edit.setMinimumWidth(0)
    return line_edit


def create_preview_search_input(parent: QWidget | None = None) -> SearchLineEdit:
    """创建用于当前预览内容的搜索框。"""
    line_edit = SearchLineEdit(parent)
    line_edit.setPlaceholderText("搜索当前事件或原始数据")
    apply_line_edit_safe_font(line_edit)
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

        self.preview_mode_pivot = SegmentedWidget(self)
        self.preview_mode_pivot.addItem("audio", "事件")
        self.preview_mode_pivot.addItem("raw", "原始数据")
        self.preview_mode_pivot.setCurrentItem("audio")
        layout.addWidget(self.preview_mode_pivot)

        self.preview_search_input = create_preview_search_input(self)
        layout.addWidget(self.preview_search_input)

        header_layout = QHBoxLayout()
        self.preview_path_edit = create_preview_path_edit(self)
        self.reveal_file_btn = TransparentToolButton(FIF.LINK, self)
        self.reveal_file_btn.setToolTip("打开文件所在位置")
        self.reveal_file_btn.setFixedSize(32, 32)
        apply_tool_button_safe_font(self.reveal_file_btn)
        self.reveal_file_btn.setEnabled(False)
        header_layout.addWidget(self.preview_path_edit, 1)
        header_layout.addWidget(self.reveal_file_btn)
        layout.addLayout(header_layout)

        self.preview_stack = QStackedWidget(self)
        self.placeholder_panel = QWidget(self)
        placeholder_layout = QVBoxLayout(self.placeholder_panel)
        placeholder_layout.setContentsMargins(8, 8, 8, 8)
        placeholder_layout.setSpacing(0)
        self.placeholder_label = BodyLabel(DEFAULT_PREVIEW_PLACEHOLDER_TEXT, self.placeholder_panel)
        self.placeholder_label.setWordWrap(True)
        placeholder_layout.addWidget(self.placeholder_label)
        placeholder_layout.addStretch(1)
        self.preview_stack.addWidget(self.placeholder_panel)

        self.text_preview = QPlainTextEdit(self)
        self.text_preview.setReadOnly(True)
        self.text_preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.text_preview.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.text_preview.setCenterOnScroll(False)
        self.text_preview.setUndoRedoEnabled(False)
        self.text_preview.setFrameShape(QFrame.Shape.NoFrame)
        self.text_preview.setAutoFillBackground(False)
        self.text_preview.viewport().setAutoFillBackground(False)
        self.text_preview.viewport().setStyleSheet("background: transparent; border: none;")
        self.text_preview.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.text_preview.customContextMenuRequested.connect(self._show_text_menu)
        self.text_preview.verticalScrollBar().setSingleStep(18)
        self.text_preview.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.refresh_theme()
        self.text_preview.setPlainText(DEFAULT_PREVIEW_PLACEHOLDER_TEXT)
        self.preview_stack.addWidget(self.text_preview)

        self.audio_preview_panel = OverviewAudioPreviewPanel(
            summary_placeholder=audio_summary_placeholder,
            parent=self,
        )
        self.preview_stack.addWidget(self.audio_preview_panel)
        self.preview_stack.setCurrentWidget(self.placeholder_panel)
        self.audio_preview_panel.set_summary_visible(False)
        layout.addWidget(self.preview_stack, 1)
        self._is_placeholder_visible = True

    def set_audio_mode(self, is_audio_mode: bool) -> None:
        """切换当前显示的预览模式。

        Args:
            is_audio_mode: 为 ``True`` 时显示事件树，否则显示原始文本。
        """
        if self._is_placeholder_visible:
            self.audio_preview_panel.set_summary_visible(False)
            self.preview_stack.setCurrentWidget(self.placeholder_panel)
            return

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
        self.placeholder_label.setText(message)
        self.text_preview.setPlainText(message)
        self.audio_preview_panel.clear_preview()
        self.reveal_file_btn.setEnabled(False)
        self._is_placeholder_visible = True
        self.preview_stack.setCurrentWidget(self.placeholder_panel)

    def show_current_preview(self) -> None:
        """按当前选中的 tab 展示预览内容。"""
        self._is_placeholder_visible = False
        self.set_audio_mode((self.preview_mode_pivot.currentRouteKey() or "audio") == "audio")

    def refresh_theme(self) -> None:
        """刷新 raw 文本预览的主题样式。"""
        light_qss, dark_qss = build_raw_preview_theme_pair()
        light_text, dark_text = get_fluent_text_primary_pair()
        text_color = QColor(dark_text if qconfig.theme == Theme.DARK else light_text)

        raw_palette = self.text_preview.palette()
        raw_palette.setColor(QPalette.ColorRole.Base, QColor(0, 0, 0, 0))
        raw_palette.setColor(QPalette.ColorRole.Text, text_color)
        raw_palette.setColor(QPalette.ColorRole.WindowText, text_color)
        self.text_preview.setPalette(raw_palette)
        self.text_preview.setStyleSheet(dark_qss if qconfig.theme == Theme.DARK else light_qss)

    def _show_text_menu(self, pos: QPoint) -> None:
        """显示基于 RoundMenu 的 raw 文本右键菜单。"""
        menu = RoundMenu(parent=self.text_preview)

        copy_action = Action("复制", menu)
        copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        copy_action.setShortcutVisibleInContextMenu(True)
        copy_action.setEnabled(self.text_preview.textCursor().hasSelection())
        copy_action.triggered.connect(self.text_preview.copy)
        menu.addAction(copy_action)

        menu.addSeparator()

        select_all_action = Action("全选", menu)
        select_all_action.setShortcut(QKeySequence.StandardKey.SelectAll)
        select_all_action.setShortcutVisibleInContextMenu(True)
        select_all_action.setEnabled(bool(self.text_preview.toPlainText()))
        select_all_action.triggered.connect(self.text_preview.selectAll)
        menu.addAction(select_all_action)

        menu.exec(
            self.text_preview.viewport().mapToGlobal(pos),
            aniType=MenuAnimationType.DROP_DOWN,
        )
