"""共用外框的范围下拉与 ID 输入，模式和内容作为整体更新。"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QSizePolicy, QWidget
from qfluentwidgets import ComboBox, LineEdit, isDarkTheme, qconfig, setCustomStyleSheet, themeColor

from lol_audio_unpack.app.targets import split_ids


class _IdEdit(LineEdit):
    """由外层统一绘制边框，防止禁用状态被程序写入活动 ID。"""

    def setText(self, text: str) -> None:
        """非指定模式的写入必须改走组合控件的原子更新入口。"""
        if text and self.parent().mode != "ids":
            raise ValueError("请通过 set_scope 同时设置指定 ID 模式和内容。")
        super().setText(text)

    def paintEvent(self, event) -> None:
        QLineEdit.paintEvent(self, event)


class ScopeInput(QWidget):
    """展示独立的类别范围，非指定模式的草稿不参与有效输入。"""

    changed = Signal()
    MODES = ("none", "all", "ids")

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        """创建保持单行高度的范围控件。"""
        super().__init__(parent)
        self.label = label
        self.mode = "none"
        self._draft = ""
        self.setMinimumWidth(250)
        self.setFixedHeight(33)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.selector = ComboBox(self)
        self.selector.addItems(["不处理", "全部", "指定 ID"])
        self.selector.setFixedWidth(98)
        self.selector.setAccessibleName(f"{label}范围")
        self.edit = _IdEdit(self)
        self.edit.setMinimumWidth(90)
        self.edit.setClearButtonEnabled(True)
        self.edit.setAccessibleName(f"{label} ID")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(1)
        layout.addWidget(self.selector)
        layout.addWidget(self.edit, 1)
        self.selector.installEventFilter(self)
        self.edit.installEventFilter(self)
        self.selector.currentIndexChanged.connect(self._change_mode)
        self.edit.textChanged.connect(self._change_text)
        self.set_scope("none")
        self._refresh_style()
        qconfig.themeChanged.connect(self._refresh_style)

    def set_scope(self, mode: str, text: str = "") -> None:
        """原子设置模式与内容，拒绝非指定模式携带活动 ID。

        Args:
            mode: none、all 或 ids。
            text: 指定模式的输入原文，可包含中英文逗号。
        """
        if mode not in self.MODES or (mode != "ids" and text):
            raise ValueError("范围模式与 ID 内容不一致。")
        blockers = [QSignalBlocker(self.selector), QSignalBlocker(self.edit)]
        self.mode = mode
        if mode == "ids":
            self._draft = text
        self.selector.setCurrentIndex(self.MODES.index(mode))
        QLineEdit.setText(self.edit, text)
        self.edit.setEnabled(mode == "ids")
        hint = {"none": "无需填写 ID", "all": f"全部{self.label}", "ids": "ID，用逗号分隔"}
        self.edit.setPlaceholderText(hint[mode])
        self.edit.clearButton.setVisible(mode == "ids" and bool(text) and self.edit.hasFocus())
        del blockers
        self.changed.emit()
        self.update()

    def reset(self) -> None:
        """清空缓存并恢复不处理。"""
        self._draft = ""
        self.set_scope("none")

    def tokens(self) -> tuple[str, ...]:
        """返回当前有效文本，不读取非指定模式下的草稿缓存。"""
        return split_ids(self.edit.text()) if self.mode == "ids" else ()

    def _change_mode(self, index: int) -> None:
        mode = self.MODES[index]
        if self.mode == "ids":
            self._draft = self.edit.text()
        self.set_scope(mode, self._draft if mode == "ids" else "")

    def _change_text(self, text: str) -> None:
        if self.mode != "ids":
            # Qt 的其他程序化编辑入口也不能绕过模式约束。
            blocker = QSignalBlocker(self.edit)
            QLineEdit.setText(self.edit, "")
            del blocker
            return
        self._draft = text
        self.changed.emit()

    def _refresh_style(self, *_args) -> None:
        style = "border: none; border-radius: 0px; background: transparent;"
        for widget, name in ((self.selector, "ComboBox"), (self.edit, "LineEdit")):
            selectors = ", ".join(f"{name}{state}" for state in ("", ":hover", ":focus", ":disabled", ":pressed"))
            sheet = f"{selectors} {{ {style} }}"
            setCustomStyleSheet(widget, sheet, sheet)
        self.update()

    def eventFilter(self, obj, event) -> bool:
        """两部分共用外层焦点反馈。"""
        if event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut, QEvent.Type.Enter, QEvent.Type.Leave):
            self.update()
        return super().eventFilter(obj, event)

    def paintEvent(self, event) -> None:
        """绘制唯一外框和内部细分隔线。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        dark = isDarkTheme()
        stroke = QColor(255, 255, 255, 28) if dark else QColor(0, 0, 0, 28)
        painter.setPen(QPen(stroke, 1))
        painter.setBrush(QColor("#343434") if dark else QColor("#ffffff"))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 5, 5)
        x = self.selector.geometry().right() + 1
        painter.drawLine(x, 7, x, self.height() - 7)
        if self.edit.hasFocus() or self.selector.hasFocus():
            painter.setPen(QPen(themeColor(), 2))
            painter.drawLine(5, self.height() - 1, self.width() - 5, self.height() - 1)
