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
    build_audio_preview_nodes,
    build_audio_preview_summary_text,
    build_overview_item_text,
    build_preview_path_text,
    collect_available_audio_ids,
    create_preview_path_edit,
    should_display_overview_row,
)


def test_build_overview_item_text_matches_entity_name() -> None:
    """列表主文案应只展示实体名称。"""
    row = {
        "name": "阿狸·九尾妖狐",
        "alias": "Ahri",
        "mapping_file": r"H:\output\hashes\16.5\champions\103.json",
    }

    assert build_overview_item_text(row) == "阿狸·九尾妖狐"


def test_build_preview_path_text_returns_full_path() -> None:
    """预览区域顶部应直接显示完整路径。"""
    path = Path(r"H:\output\hashes\16.5\champions\103.json")

    assert build_preview_path_text(None) == ""
    assert build_preview_path_text(path) == str(path)


def test_should_display_overview_row_accepts_any_valid_entity_row() -> None:
    """实体总览页展示全部有效实体，不依赖 mapping 状态过滤。"""
    assert should_display_overview_row({"id": "1", "mapping": "已存在", "mapping_file": ""}) is True
    assert should_display_overview_row({"id": "1", "mapping": "未存在", "mapping_file": r"H:\x\1.json"}) is True
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


def test_collect_available_audio_ids_reads_nested_wem_stems(tmp_path) -> None:
    """应从实体输出目录递归收集所有现存的 wem 文件 ID。"""
    (tmp_path / "267000·基础皮肤" / "VO").mkdir(parents=True)
    (tmp_path / "267000·基础皮肤" / "VO" / "1147440684.wem").write_bytes(b"")
    (tmp_path / "267000·基础皮肤" / "VO" / "1277084246.wem").write_bytes(b"")
    (tmp_path / "267001·皮肤1" / "SFX").mkdir(parents=True)
    (tmp_path / "267001·皮肤1" / "SFX" / "noise.txt").write_text("skip", encoding="utf-8")
    (tmp_path / "267001·皮肤1" / "SFX" / "987654321.wem").write_bytes(b"")

    assert collect_available_audio_ids((tmp_path,)) == {
        "1147440684",
        "1277084246",
        "987654321",
    }


def test_build_audio_preview_nodes_preserves_skin_event_hierarchy_and_availability() -> None:
    """试听树节点应保留 skins 原始层级，并按本地资源标记可点击状态。"""
    mapping_data = {
        "skins": {
            "1000": {
                "events": {
                    "Annie_Base_VO": {
                        "Play_vo_Annie_Attack2DGeneral": [118669424, 223585177],
                    },
                    "Annie_Base_SFX": {
                        "Play_sfx_Annie_AnnieQ_OnCast": [214822182],
                    },
                }
            }
        }
    }

    nodes, stats = build_audio_preview_nodes(mapping_data, {"118669424", "214822182"})

    assert build_audio_preview_summary_text(stats) == "皮肤 1 · 类型 2 · 事件 2 · ID 3 · 可试听 2"
    assert [node.label for node in nodes] == ["1000"]
    assert nodes[0].children[0].label == "events"
    assert [node.label for node in nodes[0].children[0].children] == [
        "Annie_Base_VO",
        "Annie_Base_SFX",
    ]

    vo_event = nodes[0].children[0].children[0].children[0]
    assert vo_event.label == "Play_vo_Annie_Attack2DGeneral"
    assert [child.audio_id for child in vo_event.children] == ["118669424", "223585177"]
    assert [child.is_available for child in vo_event.children] == [True, False]


def test_create_preview_path_edit_uses_fluent_line_edit() -> None:
    """预览路径输入框应使用 Fluent LineEdit 以跟随主题。"""
    widget = create_preview_path_edit()

    assert isinstance(widget, LineEdit)
    assert widget.isReadOnly() is True


def test_overview_page_load_preview_populates_audio_tree_and_summary() -> None:
    """加载预览后应同步更新 Raw 文本、试听树与摘要信息。"""
    app = QApplication.instance() or QApplication([])
    page = OverviewPage()
    page._loader = Mock()
    page._loader.load_mapping_preview.return_value = (
        Path(r"H:\output\hashes\16.5\champions\1.yml"),
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
    assert page.preview_path_edit.text() == r"H:\output\hashes\16.5\champions\1.yml"
    assert page.text_preview.toPlainText() == "raw-preview"
    assert page.audio_preview_summary_label.text() == "皮肤 1 · 类型 1 · 事件 1 · ID 2 · 可试听 1"
    assert page.audio_preview_tree.topLevelItemCount() == 1

    skin_item = page.audio_preview_tree.topLevelItem(0)
    assert skin_item.text(0) == "1000"
    id_item = skin_item.child(0).child(0).child(0).child(0)
    assert page.audio_preview_tree.itemWidget(id_item, 0) is None
    assert id_item.text(0) == "▶"
    assert id_item.text(1) == "118669424"
    assert bool(id_item.flags() & Qt.ItemIsEnabled) is True

    unavailable_item = skin_item.child(0).child(0).child(0).child(1)
    assert unavailable_item.text(1) == "223585177"
    assert bool(unavailable_item.flags() & Qt.ItemIsEnabled) is False


def test_overview_page_audio_leaf_click_only_triggers_for_enabled_leaf() -> None:
    """试听树点击只应对可试听叶子项生效。"""
    page = OverviewPage()
    triggered_ids: list[str] = []
    page._handle_audio_preview_request = triggered_ids.append
    page._loader = Mock()
    page._loader.load_mapping_preview.return_value = (
        Path(r"H:\output\hashes\16.5\champions\1.yml"),
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

    skin_item = page.audio_preview_tree.topLevelItem(0)
    available_item = skin_item.child(0).child(0).child(0).child(0)
    unavailable_item = skin_item.child(0).child(0).child(0).child(1)

    page._on_audio_preview_item_clicked(available_item, 0)
    page._on_audio_preview_item_clicked(available_item, 1)
    page._on_audio_preview_item_clicked(unavailable_item, 0)
    page._on_audio_preview_item_clicked(unavailable_item, 1)

    assert triggered_ids == ["118669424", "118669424"]
