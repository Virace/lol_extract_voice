"""测试事件映射页面的显示文案辅助逻辑。"""

from pathlib import Path

from lol_audio_unpack.gui.view.mapping_page import (
    build_mapping_item_text,
    build_mapping_preview_path_text,
    should_display_mapping_row,
)


def test_build_mapping_item_text_matches_unpack_page_name() -> None:
    """列表文案应与解包页统一，只展示实体名称。"""
    row = {
        "name": "阿狸·九尾妖狐",
        "alias": "Ahri",
        "mapping_file": r"H:\output\hashes\16.5\champions\103.json",
    }

    assert build_mapping_item_text(row) == "阿狸·九尾妖狐"


def test_build_mapping_preview_path_text_returns_full_path() -> None:
    """预览区域顶部应直接显示完整路径。"""
    path = Path(r"H:\output\hashes\16.5\champions\103.json")

    assert build_mapping_preview_path_text(None) == ""
    assert build_mapping_preview_path_text(path) == str(path)


def test_should_display_mapping_row_only_depends_on_mapping_status() -> None:
    """映射页列表只展示已存在映射的实体。"""
    assert should_display_mapping_row({"mapping": "已存在", "mapping_file": ""}) is True
    assert should_display_mapping_row({"mapping": "未存在", "mapping_file": r"H:\x\1.json"}) is False
