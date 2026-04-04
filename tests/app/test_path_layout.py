"""`app.path_layout` 路径布局规则测试。"""

from __future__ import annotations

import pytest

from lol_audio_unpack.app import path_layout


def test_get_output_dir_name() -> None:
    assert path_layout.get_output_dir_name("champion") == "champions"
    assert path_layout.get_output_dir_name("map") == "maps"


def test_get_game_dir_name() -> None:
    assert path_layout.get_game_dir_name("champion") == "Champions"
    assert path_layout.get_game_dir_name("map") == "Maps"


def test_format_folder_names() -> None:
    assert path_layout.format_entity_folder_name("1", "annie", "安妮") == "1·annie·安妮"
    assert path_layout.format_entity_folder_name("1", "annie", "安妮", "黑暗之女") == "1·annie·安妮·黑暗之女"
    assert path_layout.format_sub_entity_folder_name("1001", "默认皮肤") == "1001·默认皮肤"


def test_unknown_entity_type_raises() -> None:
    with pytest.raises(ValueError):
        path_layout.get_output_dir_name("unknown")
