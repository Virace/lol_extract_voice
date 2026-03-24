"""测试实体总览页面的显示文案辅助逻辑。"""

from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget
from qfluentwidgets import Theme, setTheme
from qfluentwidgets import theme as current_theme

from lol_audio_unpack.gui.view.overview_page import (
    _build_status_badge_styles,
    _create_status_badge,
    build_overview_item_text,
    build_preview_path_text,
    should_display_overview_row,
)


def test_build_overview_item_text_matches_entity_name() -> None:
    """列表主文案应只展示实体名称。"""
    sample_mapping_path = Path("hashes") / "16.5" / "champions" / "103.json"
    row = {
        "name": "阿狸·九尾妖狐",
        "alias": "Ahri",
        "mapping_file": str(sample_mapping_path),
    }

    assert build_overview_item_text(row) == "阿狸·九尾妖狐"


def test_build_preview_path_text_returns_full_path(tmp_path) -> None:
    """预览区域顶部应直接显示完整路径。"""
    path = tmp_path / "hashes" / "16.5" / "champions" / "103.json"

    assert build_preview_path_text(None) == ""
    assert build_preview_path_text(path) == str(path)


def test_should_display_overview_row_accepts_any_valid_entity_row(tmp_path) -> None:
    """实体总览页展示全部有效实体，不依赖 mapping 状态过滤。"""
    sample_mapping_path = tmp_path / "hashes" / "16.5" / "champions" / "1.json"
    assert should_display_overview_row({"id": "1", "mapping": "已存在", "mapping_file": ""}) is True
    assert should_display_overview_row({"id": "1", "mapping": "未存在", "mapping_file": str(sample_mapping_path)}) is True
    assert should_display_overview_row({"id": "", "mapping": "已存在"}) is False


def test_build_status_badge_styles_switches_foreground_with_theme() -> None:
    """状态徽章应为亮暗主题分别生成不同前景色与底色。"""
    light_qss, dark_qss = _build_status_badge_styles("已存在")

    assert "background-color: #0F7B0F;" in light_qss
    assert "color: #FFFFFF;" in light_qss
    assert "background-color: #6CCB5F;" in dark_qss
    assert "color: #111111;" in dark_qss


def test_create_status_badge_updates_with_theme_switch() -> None:
    """状态徽章应注册到主题系统并在切换后刷新样式。"""
    app = QApplication.instance() or QApplication([])
    original_theme = current_theme()
    parent = QWidget()

    try:
        setTheme(Theme.LIGHT)
        badge = _create_status_badge("audio", "已存在", parent)
        assert "background-color: #0F7B0F;" in badge.styleSheet()
        assert "color: #FFFFFF;" in badge.styleSheet()

        setTheme(Theme.DARK)
        app.processEvents()

        assert "background-color: #6CCB5F;" in badge.styleSheet()
        assert "color: #111111;" in badge.styleSheet()
    finally:
        setTheme(original_theme)
