"""试听树控制按钮图标测试。"""

from __future__ import annotations

from contextlib import contextmanager

from PySide6.QtCore import QRect
from qfluentwidgets import qconfig

from lol_audio_unpack.gui.components.preview_tree import (
    PreviewTreeView,
    _build_active_row_color,
    _build_audio_control_colors,
    _build_progress_fill_color,
)
from lol_audio_unpack.gui.theme import apply_accent_preset, apply_shell_mode, get_accent_preset


@contextmanager
def _restore_theme_state():
    """在测试结束后恢复 qconfig 主题状态。"""
    previous_theme = qconfig.themeMode.value
    previous_color = qconfig.themeColor.value
    try:
        yield
    finally:
        qconfig.set(qconfig.themeMode, previous_theme)
        qconfig.set(qconfig.themeColor, previous_color)


def test_preview_tree_stop_icon_rect_is_centered(qtbot) -> None:
    view = PreviewTreeView()
    qtbot.addWidget(view)
    button_rect = QRect(10, 20, 18, 18)

    stop_rect = view._stop_icon_rect(button_rect)

    assert stop_rect.width() == stop_rect.height()
    assert stop_rect.width() > 0
    assert stop_rect.center() == button_rect.center()


def test_preview_tree_accent_helpers_use_preset_tones_in_light_mode() -> None:
    """试听树活动态配色应来自固定 preset tone，而不是直接使用 primary 色。"""
    with _restore_theme_state():
        apply_shell_mode("Light")
        apply_accent_preset("orange")
        preset = get_accent_preset("orange")

        row_color = _build_active_row_color(is_dark=False)
        progress_color = _build_progress_fill_color(is_dark=False, is_playing=True)
        button_background, icon_color = _build_audio_control_colors(is_dark=False)

        expected_row = preset.scale.color(100)
        expected_row.setAlpha(38)
        expected_progress = preset.scale.color(300)
        expected_progress.setAlpha(72)
        expected_button = preset.scale.color(100)
        expected_button.setAlpha(46)
        expected_icon = preset.scale.color(700)

        assert row_color == expected_row
        assert progress_color == expected_progress
        assert button_background == expected_button
        assert icon_color == expected_icon
