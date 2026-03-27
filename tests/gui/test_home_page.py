"""测试首页卡片的展示与跳转语义。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentIcon as FIF

from lol_audio_unpack.gui.common.gui_config import GuiConfig
from lol_audio_unpack.gui.view import home_page as home_page_module
from lol_audio_unpack.gui.view.home_page import ClickableCard, HomePage
from lol_audio_unpack.utils.runtime_paths import detect_runtime_paths


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


def test_home_page_relative_output_path_follows_runtime_launch_root(monkeypatch, qtbot, tmp_path: Path) -> None:
    """首页相对输出目录应基于共享 runtime 的默认根目录解析。"""
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(HomePage, "_start_background_check", lambda self: None)
    monkeypatch.setattr(
        home_page_module,
        "detect_runtime_paths",
        lambda: detect_runtime_paths(
            is_frozen=True,
            cwd=tmp_path / "shortcut-workdir",
            executable=tmp_path / "bundle" / "LolAudioUnpack.exe",
        ),
    )
    cfg = GuiConfig(dev_mode=True)
    cfg.output_path = r".\custom-output"
    page = HomePage(cfg)
    qtbot.addWidget(page)

    assert page._resolve_output_path() == (tmp_path / "bundle" / "custom-output").resolve(strict=False)
