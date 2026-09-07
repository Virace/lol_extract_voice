"""实体总览右侧资源预览壳层与资源信息对话框。"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QPalette, QTextOption
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QPlainTextEdit,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action,
    BodyLabel,
    CaptionLabel,
    LineEdit,
    MenuAnimationType,
    PrimaryPushButton,
    PushButton,
    RoundMenu,
    SearchLineEdit,
    SegmentedWidget,
    Theme,
    TransparentToolButton,
    qconfig,
)
from qfluentwidgets import FluentIcon as FIF

from lol_audio_unpack.gui.common.font_compat import apply_line_edit_safe_font, apply_tool_button_safe_font
from lol_audio_unpack.gui.common.styles import get_fluent_frame_stroke_pair, get_fluent_text_primary_pair
from lol_audio_unpack.gui.controllers.overview_preview import (
    ALL_AUDIO_PREVIEW_MODE,
    EVENT_PREVIEW_MODE,
    RAW_PREVIEW_MODE,
)
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
    """创建跟随 Fluent 主题的只读预览来源路径输入框。"""
    line_edit = LineEdit(parent)
    line_edit.setAccessibleName("预览资源路径")
    line_edit.setReadOnly(True)
    line_edit.setClearButtonEnabled(False)
    line_edit.setPlaceholderText(DEFAULT_PREVIEW_PLACEHOLDER_TEXT)
    line_edit.setMinimumWidth(0)
    return line_edit


def create_preview_search_input(parent: QWidget | None = None) -> SearchLineEdit:
    """创建用于当前预览内容的搜索框。"""
    line_edit = SearchLineEdit(parent)
    line_edit.setAccessibleName("预览搜索")
    line_edit.setPlaceholderText("搜索当前事件或原始数据")
    apply_line_edit_safe_font(line_edit)
    return line_edit


class ResourceInfoDialog(QDialog):
    """展示当前实体的文件、映射和引用统计。"""

    open_requested = Signal(object)

    def __init__(
        self,
        *,
        details: Mapping[str, str],
        source_path: Path | None,
        audio_roots: tuple[Path, ...] = (),
        parent: QWidget | None = None,
    ) -> None:
        """初始化资源信息对话框。

        Args:
            details: 按显示顺序提供的标签和值。
            source_path: 可打开和复制的映射来源路径。
            audio_roots: 当前实体的音频目录。
            parent: 父级窗口。
        """
        super().__init__(parent)
        self.source_path = source_path
        self.setWindowTitle("资源信息")
        self.setModal(False)
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        title = BodyLabel("资源信息", self)
        title_font = title.font()
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(8)
        for name, value in details.items():
            key_label = CaptionLabel(str(name), self)
            value_label = BodyLabel(str(value), self)
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(key_label, value_label)
        layout.addLayout(form)

        for number, root in enumerate(audio_roots, start=1):
            location = create_preview_path_edit(self)
            location.setText(str(root))
            location.setCursorPosition(0)
            location.setToolTip(str(root))
            location.setAccessibleName(f"音频目录 {number}")
            open_button = TransparentToolButton(FIF.FOLDER, self)
            open_button.setToolTip("打开音频目录")
            open_button.setAccessibleName(f"打开音频目录 {number}")
            open_button.setFixedSize(32, 32)
            open_button.clicked.connect(lambda _checked=False, path=root: self.open_requested.emit(path))
            path_row = QHBoxLayout()
            path_row.setSpacing(6)
            path_row.addWidget(location, 1)
            path_row.addWidget(open_button)
            layout.addWidget(CaptionLabel("音频位置" if len(audio_roots) == 1 else f"音频位置 {number}", self))
            layout.addLayout(path_row)
        if not audio_roots:
            layout.addWidget(CaptionLabel("暂无可用音频目录", self))

        source_label = CaptionLabel("映射来源", self)
        self.source_edit = create_preview_path_edit(self)
        source_text = str(source_path) if source_path is not None else "暂无映射来源"
        self.source_edit.setText(source_text)
        self.source_edit.setCursorPosition(0)
        self.source_edit.setToolTip(source_text if source_path is not None else "")
        self.source_edit.setAccessibleName("映射来源路径")
        source_row = QHBoxLayout()
        source_row.setContentsMargins(0, 0, 0, 0)
        source_row.setSpacing(6)
        source_row.addWidget(self.source_edit, 1)
        layout.addWidget(source_label)
        layout.addLayout(source_row)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 6, 0, 0)
        action_row.setSpacing(8)
        self.copy_source_btn = PushButton("复制来源", self)
        self.copy_source_btn.setEnabled(source_path is not None)
        self.copy_source_btn.clicked.connect(self._copy_source)
        self.open_source_btn = PushButton("打开来源", self)
        self.open_source_btn.setEnabled(source_path is not None)
        self.open_source_btn.clicked.connect(lambda: self.open_requested.emit(self.source_path))
        close_btn = PrimaryPushButton("关闭", self)
        close_btn.clicked.connect(self.close)
        action_row.addWidget(self.copy_source_btn)
        action_row.addWidget(self.open_source_btn)
        action_row.addStretch(1)
        action_row.addWidget(close_btn)
        layout.addLayout(action_row)
        self.refresh_theme()

    def refresh_theme(self) -> None:
        """让原生对话框底色与 Fluent 子控件保持同一深浅主题。"""
        palette = self.palette()
        dark = qconfig.theme == Theme.DARK
        palette.setColor(QPalette.ColorRole.Window, QColor("#292929" if dark else "#FFFFFF"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(get_fluent_text_primary_pair()[int(dark)]))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

    def _copy_source(self) -> None:
        """复制当前映射来源路径。"""
        if self.source_path is not None:
            QApplication.clipboard().setText(str(self.source_path))


class OverviewPreviewPanel(QWidget):
    """承载总览页右侧 Tab、搜索/来源槽位和资源预览。"""

    resource_source_open_requested = Signal(object)

    def __init__(self, *, audio_summary_placeholder: str, parent: QWidget | None = None) -> None:
        """初始化右侧资源预览面板。

        Args:
            audio_summary_placeholder: 事件树摘要默认文案。
            parent: 父级控件。
        """
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.preview_mode_pivot = SegmentedWidget(self)
        self.preview_mode_pivot.setAccessibleName("预览模式切换")
        self.preview_mode_pivot.addItem(EVENT_PREVIEW_MODE, "事件")
        self.preview_mode_pivot.addItem(ALL_AUDIO_PREVIEW_MODE, "全部音频")
        self.preview_mode_pivot.addItem(RAW_PREVIEW_MODE, "原始数据")
        self.preview_mode_pivot.setCurrentItem(EVENT_PREVIEW_MODE)
        layout.addWidget(self.preview_mode_pivot)

        # 搜索和原始来源共用同一高度槽位，避免 raw 模式留下无作用的禁用搜索框。
        self.preview_search_stack = QStackedWidget(self)
        self.preview_search_stack.setObjectName("OverviewPreviewSearchStack")
        self.search_controls = QWidget(self.preview_search_stack)
        search_layout = QHBoxLayout(self.search_controls)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(6)
        self.preview_search_input = create_preview_search_input(self.search_controls)
        self.resource_info_btn = TransparentToolButton(FIF.INFO, self.search_controls)
        self.resource_info_btn.setAccessibleName("资源信息")
        self.resource_info_btn.setToolTip("查看当前实体的路径、文件统计和事件引用")
        self.resource_info_btn.setFixedSize(32, 32)
        apply_tool_button_safe_font(self.resource_info_btn)
        search_layout.addWidget(self.preview_search_input, 1)
        search_layout.addWidget(self.resource_info_btn)
        self.preview_search_stack.addWidget(self.search_controls)

        self.raw_controls = QWidget(self.preview_search_stack)
        raw_layout = QHBoxLayout(self.raw_controls)
        raw_layout.setContentsMargins(0, 0, 0, 0)
        raw_layout.setSpacing(6)
        self.preview_path_edit = create_preview_path_edit(self.raw_controls)
        self.reveal_file_btn = TransparentToolButton(FIF.LINK, self.raw_controls)
        self.reveal_file_btn.setAccessibleName("打开当前预览资源位置")
        self.reveal_file_btn.setToolTip("打开映射文件位置")
        self.reveal_file_btn.setFixedSize(32, 32)
        apply_tool_button_safe_font(self.reveal_file_btn)
        self.reveal_file_btn.setEnabled(False)
        raw_layout.addWidget(self.preview_path_edit, 1)
        raw_layout.addWidget(self.reveal_file_btn)
        self.preview_search_stack.addWidget(self.raw_controls)
        self.preview_search_stack.setCurrentWidget(self.search_controls)
        layout.addWidget(self.preview_search_stack)

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
        self.text_preview.setAccessibleName("原始映射数据")
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
        self.audio_preview_panel.set_export_visible(False)
        layout.addWidget(self.preview_stack, 1)
        QWidget.setTabOrder(self.preview_mode_pivot, self.preview_search_input)
        QWidget.setTabOrder(self.preview_search_input, self.resource_info_btn)
        QWidget.setTabOrder(self.resource_info_btn, self.preview_path_edit)
        QWidget.setTabOrder(self.preview_path_edit, self.reveal_file_btn)
        QWidget.setTabOrder(self.reveal_file_btn, self.audio_preview_panel.audio_preview_tree)
        QWidget.setTabOrder(self.audio_preview_panel.audio_preview_tree, self.audio_preview_panel.audio_list)
        QWidget.setTabOrder(self.audio_preview_panel.audio_list, self.text_preview)

        self._resource_info_details: dict[str, str] = {}
        self._resource_info_source: Path | None = None
        self._resource_audio_roots: tuple[Path, ...] = ()
        self._resource_info_dialog: ResourceInfoDialog | None = None
        self._is_placeholder_visible = True
        self.resource_info_btn.setEnabled(False)
        self.resource_info_btn.clicked.connect(self.show_resource_info)

    def set_audio_mode(self, is_audio_mode: bool) -> None:
        """兼容旧调用方切换事件与原始数据模式。

        Args:
            is_audio_mode: 为 ``True`` 时显示事件树，否则显示原始文本。
        """
        self.set_preview_mode(EVENT_PREVIEW_MODE if is_audio_mode else RAW_PREVIEW_MODE)

    def set_preview_mode(self, mode_key: str) -> None:
        """按三种资源预览方式切换当前内容。

        Args:
            mode_key: 事件、全部音频或原始数据的稳定模式键。
        """
        mode_key = (
            mode_key
            if mode_key in {EVENT_PREVIEW_MODE, ALL_AUDIO_PREVIEW_MODE, RAW_PREVIEW_MODE}
            else EVENT_PREVIEW_MODE
        )
        if self._is_placeholder_visible:
            self.preview_stack.setCurrentWidget(self.placeholder_panel)
            self.preview_search_stack.setCurrentWidget(
                self.raw_controls if mode_key == RAW_PREVIEW_MODE else self.search_controls
            )
            self.audio_preview_panel.set_summary_visible(False)
            self.audio_preview_panel.set_export_visible(False)
            return

        if mode_key == RAW_PREVIEW_MODE:
            self.preview_search_stack.setCurrentWidget(self.raw_controls)
            self.preview_stack.setCurrentWidget(self.text_preview)
            self.audio_preview_panel.set_summary_visible(False)
            self.audio_preview_panel.set_export_visible(False)
            return

        self.preview_search_stack.setCurrentWidget(self.search_controls)
        self.audio_preview_panel.set_preview_mode(mode_key)
        self.preview_stack.setCurrentWidget(self.audio_preview_panel)
        self.audio_preview_panel.set_summary_visible(True)
        self.audio_preview_panel.set_export_visible(True)

    def set_preview_path(self, text: str) -> None:
        """同步当前映射来源路径。

        Args:
            text: 预览路径文本。
        """
        self.preview_path_edit.setText(text)
        self.preview_path_edit.setToolTip(text)

    def set_resource_info(
        self, details: Mapping[str, str], source_path: Path | None, audio_roots: tuple[Path, ...] = ()
    ) -> None:
        """更新资源信息按钮对应的当前实体快照。

        Args:
            details: 当前实体的统计标签和值。
            source_path: 当前映射来源路径；不存在时传 ``None``。
            audio_roots: 当前实体的音频目录。
        """
        self._close_resource_info_dialog()
        self._resource_info_details = {str(key): str(value) for key, value in details.items()}
        self._resource_info_source = Path(source_path) if source_path is not None else None
        self._resource_audio_roots = audio_roots
        self.resource_info_btn.setEnabled(bool(self._resource_info_details))

    def clear_resource_info(self) -> None:
        """清空资源信息快照，避免保留上一个实体的路径。"""
        self._close_resource_info_dialog()
        self._resource_info_details = {}
        self._resource_info_source = None
        self._resource_audio_roots = ()
        self.resource_info_btn.setEnabled(False)

    def show_resource_info(self) -> ResourceInfoDialog | None:
        """打开当前实体的资源信息对话框。"""
        if not self._resource_info_details:
            return None
        self._close_resource_info_dialog()
        dialog = ResourceInfoDialog(
            details=self._resource_info_details,
            source_path=self._resource_info_source,
            audio_roots=self._resource_audio_roots,
            parent=self.window() or self,
        )
        dialog.open_requested.connect(self.resource_source_open_requested)
        # 使用带 QObject 接收者的槽，父面板销毁时 Qt 会断开待处理的窗口信号。
        dialog.finished.connect(self._resource_info_dialog_finished)
        self._resource_info_dialog = dialog
        dialog.open()
        return dialog

    def show_placeholder(self, message: str) -> None:
        """显示空态提示并清理路径、资源统计和预览数据。

        Args:
            message: 要展示的占位提示。
        """
        self.preview_path_edit.clear()
        self.preview_path_edit.setToolTip("")
        self.placeholder_label.setText(message)
        self.text_preview.setPlainText(message)
        self.audio_preview_panel.clear_preview()
        self.audio_preview_panel.set_export_visible(False)
        self.reveal_file_btn.setEnabled(False)
        self.clear_resource_info()
        self._is_placeholder_visible = True
        self.preview_stack.setCurrentWidget(self.placeholder_panel)

    def show_current_preview(self) -> None:
        """按当前选中的 tab 展示预览内容。"""
        self._is_placeholder_visible = False
        self.set_preview_mode(self.preview_mode_pivot.currentRouteKey() or EVENT_PREVIEW_MODE)

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
        if dialog := getattr(self, "_resource_info_dialog", None):
            dialog.refresh_theme()

    def _close_resource_info_dialog(self) -> None:
        """关闭仍属于旧实体的资源信息窗口。"""
        dialog = self._resource_info_dialog
        if dialog is None:
            return
        self._resource_info_dialog = None
        dialog.close()

    def _resource_info_dialog_finished(self, _result: int) -> None:
        """清理已关闭的资源信息窗口引用。"""
        dialog = self.sender()
        if self._resource_info_dialog is dialog:
            self._resource_info_dialog = None
        if dialog is not None:
            dialog.deleteLater()

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


__all__ = [
    "DEFAULT_PREVIEW_PLACEHOLDER_TEXT",
    "OverviewPreviewPanel",
    "ResourceInfoDialog",
    "build_raw_preview_theme_pair",
    "create_preview_path_edit",
    "create_preview_search_input",
]
