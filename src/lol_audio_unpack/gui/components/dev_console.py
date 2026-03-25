"""隐藏开发控制台组件。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, LineEdit, PlainTextEdit, StrongBodyLabel


class DevConsoleWindow(QDialog):
    """提供轻量内部调试命令的开发控制台。"""

    command_submitted = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化开发控制台窗口。

        Args:
            parent: 宿主窗口。
        """
        super().__init__(parent)
        self.setWindowTitle("开发控制台")
        self.setModal(False)
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.resize(460, 280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = StrongBodyLabel("开发控制台", self)
        hint = CaptionLabel("输入 help 查看可用命令，回车立即执行。", self)
        hint.setWordWrap(True)

        self.command_input = LineEdit(self)
        self.command_input.setPlaceholderText("help / queue fill 5 / queue inspect")
        self.command_input.returnPressed.connect(self._submit_current_command)

        self.output_panel = PlainTextEdit(self)
        self.output_panel.setReadOnly(True)
        self.output_panel.setPlaceholderText("命令输出会显示在这里。")

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self.command_input)
        layout.addWidget(self.output_panel, 1)

    def focus_command_input(self) -> None:
        """将焦点移动到命令输入框。"""
        self.command_input.setFocus()
        self.command_input.selectAll()

    def append_output(self, text: str) -> None:
        """向输出面板追加一行文本。

        Args:
            text: 需要输出的单行文本。
        """
        normalized = text.rstrip()
        if not normalized:
            return
        self.output_panel.appendPlainText(normalized)

    def output_text(self) -> str:
        """返回当前控制台输出文本。"""
        return self.output_panel.toPlainText()

    def _submit_current_command(self) -> None:
        """提交当前输入框中的命令。"""
        command = self.command_input.text().strip()
        if not command:
            return
        self.command_input.clear()
        self.command_submitted.emit(command)
