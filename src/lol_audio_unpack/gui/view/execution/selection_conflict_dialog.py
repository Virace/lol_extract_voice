"""执行中心选择冲突确认弹窗。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
from qfluentwidgets import MessageBox, PushButton


def ask_selection_conflict_resolution(*, content: str, parent: QWidget) -> str:
    """弹出选择同步冲突弹窗，并返回用户决策。"""
    dialog = MessageBox("更新当前任务目标", content, parent)
    dialog.yesButton.setText("覆盖")
    dialog.cancelButton.setText("取消")

    merge_button = PushButton("合并", dialog.buttonGroup)
    merge_button.setAttribute(Qt.WA_LayoutUsesWidgetRect)
    dialog.buttonLayout.insertWidget(0, merge_button, 1, Qt.AlignVCenter)

    result = {"choice": "cancel"}

    def choose_merge() -> None:
        result["choice"] = "merge"
        dialog.accept()

    dialog.yesSignal.connect(lambda: result.__setitem__("choice", "replace"))
    dialog.cancelSignal.connect(lambda: result.__setitem__("choice", "cancel"))
    merge_button.clicked.connect(choose_merge)
    dialog.exec()
    return str(result["choice"])
