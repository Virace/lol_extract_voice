"""固定 accent preset 与主题运行时入口测试。"""

from __future__ import annotations

from contextlib import contextmanager

from qfluentwidgets import Theme, qconfig

from lol_audio_unpack.gui.theme.presets import (
    DEFAULT_ACCENT_PRESET_ID,
    get_accent_preset,
    list_accent_presets,
    resolve_legacy_accent_preset,
)
from lol_audio_unpack.gui.theme.runtime import (
    apply_accent_preset,
    apply_shell_mode,
    resolve_progress_palette,
)


@contextmanager
def _restore_qconfig_theme_state():
    """在测试结束后恢复 qconfig 的主题状态。"""
    previous_theme = qconfig.themeMode.value
    previous_color = qconfig.themeColor.value
    try:
        yield
    finally:
        qconfig.set(qconfig.themeMode, previous_theme)
        qconfig.set(qconfig.themeColor, previous_color)


def test_list_accent_presets_returns_expected_ids() -> None:
    """固定 accent preset 列表应与产品约定一致。"""
    assert [preset.id for preset in list_accent_presets()] == [
        "purple",
        "blue",
        "green",
        "orange",
    ]


def test_apply_shell_mode_and_accent_preset_updates_qconfig() -> None:
    """运行时入口应同步更新 qconfig 的主题模式与强调色。"""
    with _restore_qconfig_theme_state():
        theme = apply_shell_mode("Dark")
        color = apply_accent_preset("green")

        assert theme == Theme.DARK
        assert qconfig.themeMode.value == Theme.DARK
        assert color.name().lower() == get_accent_preset("green").primary_hex.lower()
        assert qconfig.themeColor.value.name().lower() == get_accent_preset("green").primary_hex.lower()


def test_resolve_progress_palette_returns_complete_palette() -> None:
    """Progress palette 解析结果应包含完整颜色槽位。"""
    palette = resolve_progress_palette(mode="Dark", preset_id="blue")

    assert palette.track_base
    assert palette.track_border
    assert palette.fill_main
    assert palette.fill_emphasis
    assert palette.text_primary
    assert palette.text_secondary
    assert palette.button_icon
    assert palette.button_hover
    assert palette.button_pressed


def test_resolve_legacy_accent_preset_falls_back_to_default_for_unknown_color() -> None:
    """无法识别的旧颜色应回退到默认 preset。"""
    assert resolve_legacy_accent_preset("#009faa") == DEFAULT_ACCENT_PRESET_ID
