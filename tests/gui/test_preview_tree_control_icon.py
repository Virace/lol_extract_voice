"""试听树控制按钮图标测试。"""

from __future__ import annotations

from PySide6.QtCore import QRect

from lol_audio_unpack.gui.components.preview_tree import PreviewTreeView


def test_preview_tree_stop_icon_rect_is_centered(qtbot) -> None:
    view = PreviewTreeView()
    qtbot.addWidget(view)
    button_rect = QRect(10, 20, 18, 18)

    stop_rect = view._stop_icon_rect(button_rect)

    assert stop_rect.width() == stop_rect.height()
    assert stop_rect.width() > 0
    assert stop_rect.center() == button_rect.center()
