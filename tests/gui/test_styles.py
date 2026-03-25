"""测试 GUI 公共样式基线。"""

from lol_audio_unpack.gui.common.styles import (
    build_fluent_list_shell_theme_pair,
    build_fluent_tree_shell_theme_pair,
    get_fluent_frame_stroke_pair,
    get_fluent_neutral_surface_pair,
    get_fluent_text_primary_pair,
)


def test_get_fluent_frame_stroke_pair_matches_audited_tree_view_border_tokens() -> None:
    """公共描边色应对齐已核对的 qfluentwidgets TreeView 边框值。"""
    light_stroke, dark_stroke = get_fluent_frame_stroke_pair()

    assert light_stroke == "rgba(0, 0, 0, 15)"
    assert dark_stroke == "rgba(255, 255, 255, 21)"


def test_get_fluent_text_primary_pair_matches_audited_view_text_colors() -> None:
    """公共主文本色应对齐已核对的 List/Tree 默认前景色。"""
    light_text, dark_text = get_fluent_text_primary_pair()

    assert light_text == "#242424"
    assert dark_text == "#F5F5F5"


def test_get_fluent_neutral_surface_pair_provides_subtle_and_emphasis_variants() -> None:
    """公共中性 surface 应提供列表和树都能复用的轻重两档语义。"""
    subtle_idle = get_fluent_neutral_surface_pair("subtle_idle")
    subtle_hover = get_fluent_neutral_surface_pair("subtle_hover")
    subtle_selected = get_fluent_neutral_surface_pair("subtle_selected")
    emphasis_hover = get_fluent_neutral_surface_pair("emphasis_hover")
    emphasis_selected = get_fluent_neutral_surface_pair("emphasis_selected")

    assert subtle_idle == ((0, 0, 0, 8), (255, 255, 255, 12))
    assert subtle_hover == ((0, 0, 0, 10), (255, 255, 255, 14))
    assert subtle_selected == ((0, 0, 0, 18), (255, 255, 255, 22))
    assert emphasis_hover == ((0, 0, 0, 15), (255, 255, 255, 20))
    assert emphasis_selected == ((0, 0, 0, 26), (255, 255, 255, 36))


def test_build_fluent_list_shell_theme_pair_uses_audited_list_view_shell_baseline() -> None:
    """列表壳层 recipe 应复用已核对的 ListView 默认 padding 基线。"""
    light_qss, dark_qss = build_fluent_list_shell_theme_pair()

    assert "QListView {" in light_qss
    assert "padding: 0 4px;" in light_qss
    assert "padding-left: 11px;" in light_qss
    assert "padding-right: 11px;" in light_qss
    assert "min-height: 35px;" in light_qss
    assert "border: none;" in dark_qss
    assert "background-color: transparent;" in light_qss
    assert "background-color: transparent;" in dark_qss


def test_build_fluent_tree_shell_theme_pair_uses_audited_tree_view_border_tokens() -> None:
    """树壳层 recipe 应复用已核对的 TreeView 边框与右侧 padding 基线。"""
    light_qss, dark_qss = build_fluent_tree_shell_theme_pair()

    assert "QTreeView {" in light_qss
    assert "padding: 0 5px 0 0;" in light_qss
    assert "border: 1px solid rgba(0, 0, 0, 15);" in light_qss
    assert "padding-left: 20px;" in light_qss
    assert "border: 1px solid rgba(255, 255, 255, 21);" in dark_qss
