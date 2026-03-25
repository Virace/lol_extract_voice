"""测试主窗口宿主中的基础预览树。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, qconfig, setTheme, setThemeColor

from lol_audio_unpack.gui.components.preview_tree import PreviewTreeModel
from lol_audio_unpack.gui.window import MainWindow


def _configure_gui_app(app: QApplication, *, theme: Theme) -> None:
    """按 GUI 启动链的关键步骤配置应用实例。"""
    font = QFont("Microsoft YaHei")
    font.setPixelSize(14)
    font.setWeight(QFont.Weight.Normal)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)
    qconfig.set(qconfig.themeMode, theme)
    setTheme(theme)
    color = QColor("#2E75FF")
    qconfig.set(qconfig.themeColor, color)
    setThemeColor(color)


def _attach_preview_loader(window: MainWindow, tmp_path: Path) -> None:
    """给 OverviewPage 注入稳定的预览数据来源。"""
    preview_path = tmp_path / "hashes" / "16.5" / "champions" / "1.msgpack"
    loader = Mock()
    loader.load_mapping_preview.return_value = (
        preview_path,
        {
            "skins": {
                "4000": {
                    "events": {
                        "TwistedFate_Base_SFX": {
                            "Play_sfx_TwistedFate_Test": [1, 2],
                        }
                    }
                }
            }
        },
        "{\n  \"metadata\": \"window-preview\"\n}",
    )
    loader.load_available_audio_ids.return_value = {"1"}
    window.overviewInterface._loader = loader


def test_main_window_overview_preview_tree_can_expand_with_custom_preview_tree(
    qtbot, monkeypatch, tmp_path
) -> None:
    """真实主窗口宿主里，自定义试听树也应正常展开并加载子节点。"""
    app = QApplication.instance() or QApplication([])
    original_theme = qconfig.theme
    original_color = qconfig.get(qconfig.themeColor)

    monkeypatch.setattr(MainWindow, "_load_initial_data", lambda self, cfg: None)
    window = MainWindow()
    qtbot.addWidget(window)

    try:
        _configure_gui_app(app, theme=Theme.DARK)
        window._inject_mock_data()
        _attach_preview_loader(window, tmp_path)
        window.switchTo(window.overviewInterface)
        window.overviewInterface._on_preview_mode_changed("audio")
        window.resize(1280, 860)
        window.show()
        app.processEvents()

        index = window.overviewInterface._entity_lists["champions"].model().index(0, 0)
        window.overviewInterface._load_preview_for_item("champions", index)
        app.processEvents()

        tree = window.overviewInterface.audio_preview_tree
        model = tree.model()
        assert isinstance(model, PreviewTreeModel)
        assert tree.styleSheet() != ""

        root_index = model.index(0, 0)
        tree.expand(root_index)
        app.processEvents()

        assert model.rowCount(root_index) == 1
    finally:
        setTheme(original_theme)
        setThemeColor(original_color)
        app.processEvents()
