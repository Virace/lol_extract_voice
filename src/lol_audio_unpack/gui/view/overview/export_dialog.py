"""使用程序主题展示音频导出范围与覆盖选项。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
from qfluentwidgets import BodyLabel, CheckBox, MessageBoxBase, SubtitleLabel


class AudioExportDialog(MessageBoxBase):
    """让导出信息和覆盖选项共用 Fluent 主题。"""

    def __init__(self, summary: str, details: str, parent: QWidget) -> None:
        """展示冻结的导出摘要，默认跳过已有 WAV。

        Args:
            summary: 当前对象与采样格式。
            details: 导出范围、目录和文件可用性说明。
            parent: 承载模态遮罩的主窗口。
        """
        super().__init__(parent)
        self.setWindowTitle("核对音频导出")
        self.viewLayout.addWidget(SubtitleLabel("核对音频导出", self.widget))
        for text in (summary, details):
            label = BodyLabel(text, self.widget)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.viewLayout.addWidget(label)

        self.overwrite = CheckBox("覆盖本次范围内的已有 WAV（默认跳过）", self.widget)
        self.viewLayout.addWidget(self.overwrite)
        self.widget.setMinimumWidth(520)
        self.widget.setMaximumWidth(640)
        self.yesButton.setText("开始导出")
        self.cancelButton.setText("返回选择")
