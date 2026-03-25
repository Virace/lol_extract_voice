"""测试首页卡片的展示与跳转语义。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentIcon as FIF

from lol_audio_unpack.gui.common.gui_config import GuiConfig
from lol_audio_unpack.gui.view.home_page import ClickableCard, HomePage


def test_clickable_card_can_disable_jump_behavior(qtbot, monkeypatch) -> None:
    """禁用跳转后，卡片点击不应再尝试打开路径或弹出提示。"""
    QApplication.instance() or QApplication([])
    card = ClickableCard(FIF.CODE, "游戏版本", "16.5")
    qtbot.addWidget(card)
    warned: list[tuple[str, str]] = []
    monkeypatch.setattr(card, "_warn", lambda title, content: warned.append((title, content)))

    card.setJumpEnabled(False)
    card.show()
    qtbot.mouseClick(card, Qt.MouseButton.LeftButton)

    assert card.isJumpEnabled() is False
    assert card.linkIcon.isHidden() is True
    assert card.cursor().shape() == Qt.CursorShape.ArrowCursor
    assert warned == []


def test_home_page_version_card_is_display_only(monkeypatch, qtbot) -> None:
    """首页游戏版本卡片应只展示信息，不具备跳转能力。"""
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(HomePage, "_start_background_check", lambda self: None)
    page = HomePage(GuiConfig(dev_mode=True))
    qtbot.addWidget(page)

    assert page.version_card.isJumpEnabled() is False
    assert page.version_card.linkIcon.isHidden() is True
    assert page.version_card.cursor().shape() == Qt.CursorShape.ArrowCursor
