"""GUI 壳模式、强调色预设与进度条调色运行时入口。"""

from __future__ import annotations

from PySide6.QtGui import QColor
from qfluentwidgets import Theme, qconfig, setTheme, setThemeColor

from lol_audio_unpack.gui.theme.presets import (
    DEFAULT_ACCENT_PRESET_ID,
    AccentPreset,
    AccentPresetId,
    ThemeProgressPalette,
    get_accent_preset,
)

_THEME_BY_MODE = {
    "light": Theme.LIGHT,
    "dark": Theme.DARK,
    "auto": Theme.AUTO,
    "Light": Theme.LIGHT,
    "Dark": Theme.DARK,
    "Auto": Theme.AUTO,
}
_MODE_BY_THEME = {
    Theme.LIGHT: "Light",
    Theme.DARK: "Dark",
    Theme.AUTO: "Auto",
}
_runtime_state = {"accent_preset_id": DEFAULT_ACCENT_PRESET_ID}


def apply_shell_mode(mode: str) -> Theme:
    """应用当前壳模式到 QFluentWidgets。

    Args:
        mode: `Light` / `Dark` / `Auto`。

    Returns:
        Theme: 实际应用到 Fluent 的主题枚举。
    """
    theme = _THEME_BY_MODE.get(mode, Theme.AUTO)
    qconfig.set(qconfig.themeMode, theme)
    setTheme(theme)
    return theme


def shell_mode_from_theme(theme: Theme) -> str:
    """把 Fluent 主题枚举转换成 GuiConfig 使用的壳模式字符串。"""
    return _MODE_BY_THEME.get(theme, "Auto")


def apply_accent_preset(preset: AccentPresetId | str | AccentPreset) -> object:
    """把固定强调色预设应用到 QFluentWidgets。

    Args:
        preset: 预设对象或其标识。

    Returns:
        object: 实际应用到 Fluent 的 `QColor`。
    """
    resolved = preset if isinstance(preset, AccentPreset) else get_accent_preset(preset)
    _runtime_state["accent_preset_id"] = resolved.id
    color = resolved.primary_color
    qconfig.set(qconfig.themeColor, color)
    setThemeColor(color)
    return color


def current_accent_preset_id() -> AccentPresetId:
    """返回当前已应用到 Fluent 的固定强调色预设标识。"""
    return _runtime_state["accent_preset_id"]


def resolve_progress_palette(mode: str, preset_id: AccentPresetId | str) -> ThemeProgressPalette:
    """根据壳模式与 accent preset 生成进度条参考 palette。

    Args:
        mode: 当前壳模式。
        preset_id: 当前固定强调色预设。

    Returns:
        ThemeProgressPalette: 供后续自定义进度条消费的参考色槽位。
    """
    preset = get_accent_preset(preset_id)
    dark_mode = _THEME_BY_MODE.get(mode, Theme.AUTO) == Theme.DARK

    if dark_mode:
        return ThemeProgressPalette(
            track_base=QColor(20, 24, 31, 236),
            track_border=QColor(255, 255, 255, 44),
            fill_main=preset.scale.color(300),
            fill_emphasis=preset.scale.color(500),
            text_primary=QColor(245, 247, 250, 236),
            text_secondary=QColor(214, 220, 228, 220),
            button_icon=QColor(245, 247, 250, 236),
            button_hover=QColor(255, 255, 255, 24),
            button_pressed=QColor(255, 255, 255, 42),
        )

    return ThemeProgressPalette(
        track_base=QColor(242, 245, 249, 242),
        track_border=QColor(24, 36, 54, 24),
        fill_main=preset.scale.color(300),
        fill_emphasis=preset.scale.color(500),
        text_primary=QColor(34, 39, 46, 232),
        text_secondary=QColor(76, 84, 96, 222),
        button_icon=QColor(34, 39, 46, 232),
        button_hover=QColor(0, 0, 0, 16),
        button_pressed=QColor(0, 0, 0, 28),
    )
