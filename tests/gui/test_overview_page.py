"""测试实体总览页面的显示文案辅助逻辑。"""

from pathlib import Path
from unittest.mock import Mock

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget
from qfluentwidgets import LineEdit, Theme, setTheme
from qfluentwidgets import theme as current_theme

from lol_audio_unpack.gui.view.overview_page import (
    OverviewPage,
    _build_status_badge_styles,
    _create_status_badge,
    build_overview_item_text,
    build_preview_path_text,
    create_preview_path_edit,
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


def test_create_preview_path_edit_uses_fluent_line_edit() -> None:
    """预览路径输入框应使用 Fluent LineEdit 以跟随主题。"""
    widget = create_preview_path_edit()

    assert isinstance(widget, LineEdit)
    assert widget.isReadOnly() is True


def test_overview_page_load_preview_populates_audio_tree_and_summary(tmp_path) -> None:
    """加载预览后应同步更新 Raw 文本、试听树与摘要信息。"""
    app = QApplication.instance() or QApplication([])
    page = OverviewPage()
    preview_path = tmp_path / "hashes" / "16.5" / "champions" / "1.yml"
    page._loader = Mock()
    page._loader.load_mapping_preview.return_value = (
        preview_path,
        {
            "skins": {
                "1000": {
                    "events": {
                        "Annie_Base_VO": {
                            "Play_vo_Annie_Attack2DGeneral": [118669424, 223585177],
                        }
                    }
                }
            }
        },
        "raw-preview",
    )
    page._loader.load_available_audio_ids.return_value = {"118669424"}
    item = Mock()
    item.data.return_value = {
        "id": "1",
        "name": "安妮",
    }

    page._load_preview_for_item("champions", item)
    app.processEvents()

    assert isinstance(page.preview_path_edit, LineEdit)
    assert page.preview_path_edit.text() == str(preview_path)
    assert page.text_preview.toPlainText() == "raw-preview"
    assert page.audio_preview_summary_label.text() == "皮肤 1 · 类型 1 · 事件 1 · ID 2 · 可试听 1"
    model = page.audio_preview_tree.preview_model
    assert model.rowCount() == 1

    skin_index = model.index(0, 0)
    assert model.data(skin_index, Qt.DisplayRole) == "1000"
    page.audio_preview_tree.ensure_children_loaded(skin_index)
    type_index = model.index(0, 0, skin_index)
    assert model.data(type_index, Qt.DisplayRole) == "Annie_Base_VO"
    page.audio_preview_tree.ensure_children_loaded(type_index)
    event_index = model.index(0, 0, type_index)
    assert model.data(event_index, Qt.DisplayRole) == "Play_vo_Annie_Attack2DGeneral"
    page.audio_preview_tree.ensure_children_loaded(event_index)
    id_index = model.index(0, 0, event_index)
    unavailable_index = model.index(1, 0, event_index)
    assert model.data(id_index, Qt.DisplayRole) == "118669424"
    assert model.data(unavailable_index, Qt.DisplayRole) == "223585177"


def test_overview_page_audio_leaf_click_only_triggers_for_enabled_leaf(tmp_path) -> None:
    """试听树点击只应对可试听叶子项生效。"""
    page = OverviewPage()
    triggered_ids: list[str] = []
    preview_path = tmp_path / "hashes" / "16.5" / "champions" / "1.yml"
    page._handle_audio_preview_request = triggered_ids.append
    page._loader = Mock()
    page._loader.load_mapping_preview.return_value = (
        preview_path,
        {
            "skins": {
                "1000": {
                    "events": {
                        "Annie_Base_VO": {
                            "Play_vo_Annie_Attack2DGeneral": [118669424, 223585177],
                        }
                    }
                }
            }
        },
        "raw-preview",
    )
    page._loader.load_available_audio_ids.return_value = {"118669424"}
    item = Mock()
    item.data.return_value = {
        "id": "1",
        "name": "安妮",
    }

    page._load_preview_for_item("champions", item)

    model = page.audio_preview_tree.preview_model
    skin_index = model.index(0, 0)
    page.audio_preview_tree.ensure_children_loaded(skin_index)
    type_index = model.index(0, 0, skin_index)
    page.audio_preview_tree.ensure_children_loaded(type_index)
    event_index = model.index(0, 0, type_index)
    page.audio_preview_tree.ensure_children_loaded(event_index)
    available_index = model.index(0, 0, event_index)
    unavailable_index = model.index(1, 0, event_index)

    assert page.audio_preview_tree.try_emit_audio_request(available_index) is True
    assert page.audio_preview_tree.try_emit_audio_request(unavailable_index) is False
    assert triggered_ids == ["118669424"]
