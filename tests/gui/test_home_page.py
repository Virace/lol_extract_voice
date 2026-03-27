"""测试首页卡片的展示与跳转语义。"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentIcon as FIF

from lol_audio_unpack.gui.common.gui_config import GuiConfig
from lol_audio_unpack.gui.common.path_display import (
    format_default_relative_path,
    format_path_for_display,
)
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


def test_format_default_relative_path_uses_platform_root_label() -> None:
    """默认相对路径提示应转成平台风格的“根目录”文案。"""
    assert format_default_relative_path(r".\tools\wwiser\wwiser.pyz", platform="win32") == r"根目录\tools\wwiser\wwiser.pyz"
    assert format_default_relative_path(r".\tools\wwiser\wwiser.pyz", platform="linux") == "根目录/tools/wwiser/wwiser.pyz"


def test_clickable_card_set_path_formats_display_but_keeps_raw_path(qtbot) -> None:
    """首页卡片应保留真实跳转路径，但显示文本按平台格式化。"""
    QApplication.instance() or QApplication([])
    card = ClickableCard(FIF.FOLDER, "工具路径", "未设置")
    qtbot.addWidget(card)
    raw_path = "./tools/wwiser/wwiser.pyz"

    card.setPath(raw_path)

    assert card._raw_path == raw_path
    assert card.contentLabel.toolTip() == format_default_relative_path(raw_path)
    assert os.sep in card.contentLabel.toolTip()
    assert "根目录" in card.contentLabel.toolTip()


def test_format_path_for_display_normalizes_separators_by_platform() -> None:
    """真实路径显示应按目标平台切换分隔符风格。"""
    assert format_path_for_display("tools/wwiser/wwiser.pyz", platform="win32") == r"tools\wwiser\wwiser.pyz"
    assert format_path_for_display(r"tools\wwiser\wwiser.pyz", platform="linux") == "tools/wwiser/wwiser.pyz"


def test_clickable_card_open_relative_path_uses_runtime_launch_root(monkeypatch, qtbot, tmp_path: Path) -> None:
    """首页卡片打开相对路径时应基于 runtime launch_root，而不是 cwd。"""
    QApplication.instance() or QApplication([])
    runtime_root = tmp_path / "bundle-root"
    target_file = runtime_root / "tools" / "wwiser" / "wwiser.pyz"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_bytes(b"")

    monkeypatch.setattr(
        home_page_module,
        "detect_runtime_paths",
        lambda: detect_runtime_paths(
            is_frozen=True,
            cwd=tmp_path / "shortcut-workdir",
            executable=runtime_root / "LolAudioUnpack.exe",
        ),
    )

    opened_targets: list[str] = []
    monkeypatch.setattr(
        home_page_module.QDesktopServices,
        "openUrl",
        lambda url: opened_targets.append(url.toLocalFile()) or True,
    )

    card = ClickableCard(FIF.DEVELOPER_TOOLS, "wwiser", "未设置")
    qtbot.addWidget(card)
    card.setPath("./tools/wwiser/wwiser.pyz")

    card._open_in_explorer()

    assert [Path(item).resolve(strict=False) for item in opened_targets] == [
        target_file.parent.resolve(strict=False)
    ]
