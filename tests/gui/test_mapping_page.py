"""测试资源映射页面的显示文案辅助逻辑。"""

from lol_audio_unpack.gui.view.mapping_page import (
    build_mapping_item_text,
    should_display_mapping_row,
)


def test_build_mapping_item_text_prefers_name_and_alias_then_file_name() -> None:
    """列表文案应使用“名称·alias / 文件名”两行结构。"""
    row = {
        "name": "阿狸",
        "alias": "Ahri",
        "mapping_file": r"H:\output\hashes\16.5\champions\103.json",
    }

    assert build_mapping_item_text(row) == "阿狸·Ahri\n103.json"


def test_should_display_mapping_row_only_depends_on_mapping_status() -> None:
    """映射页列表只展示已存在映射的实体。"""
    assert should_display_mapping_row({"mapping": "已存在", "mapping_file": ""}) is True
    assert should_display_mapping_row({"mapping": "未存在", "mapping_file": r"H:\x\1.json"}) is False
