"""GUI 主题强调色与状态语义色解析。"""

from __future__ import annotations

from typing import Literal

from PySide6.QtGui import QColor
from qfluentwidgets import Theme, isDarkTheme
from qfluentwidgets.common.color import FluentSystemColor

from lol_audio_unpack.gui.theme.presets import AccentPreset, AccentPresetId, get_accent_preset
from lol_audio_unpack.gui.theme.runtime import current_accent_preset_id

SemanticColorRole = Literal["accent", "info", "success", "neutral", "caution", "critical"]

_LIGHT_REFERENCE_SURFACE = QColor("#FFFFFF")
_DARK_REFERENCE_SURFACE = QColor("#111111")
_INFO_TEXT_PAIR = (QColor("#0F6CBD"), QColor("#75B6E7"))
_NEUTRAL_TEXT_PAIR = (QColor("#616161"), QColor("#D6D6D6"))
_SRGB_LINEAR_THRESHOLD = 0.04045
_BODY_TEXT_CONTRAST_TARGET = 4.5


def _linear_channel(value: float) -> float:
    """把 sRGB 通道转换为相对亮度计算所需的线性值。"""
    return value / 12.92 if value <= _SRGB_LINEAR_THRESHOLD else ((value + 0.055) / 1.055) ** 2.4


def _relative_luminance(color: QColor) -> float:
    """计算颜色的 WCAG 相对亮度。"""
    red = _linear_channel(color.redF())
    green = _linear_channel(color.greenF())
    blue = _linear_channel(color.blueF())
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast_ratio(foreground: QColor, background: QColor) -> float:
    """计算前景色与背景色的 WCAG 对比度。"""
    lighter, darker = sorted(
        (_relative_luminance(foreground), _relative_luminance(background)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


def _pick_accent_text_color(
    preset: AccentPreset,
    tones: tuple[int, ...],
    background: QColor,
) -> QColor:
    """从预设色阶中选择满足正文对比度的第一个颜色。"""
    for tone in tones:
        color = preset.scale.color(tone)
        if _contrast_ratio(color, background) >= _BODY_TEXT_CONTRAST_TARGET:
            return color
    return preset.scale.color(tones[-1])


def get_accent_text_color_pair(
    preset_id: AccentPresetId | str | None = None,
) -> tuple[QColor, QColor]:
    """返回页面引导文字使用的亮暗主题 accent 色对。

    Args:
        preset_id: 强调色预设；为空时使用当前运行时预设。

    Returns:
        ``(light, dark)`` 主题色对，均满足正文尺寸文字的目标对比度。
    """
    preset = get_accent_preset(preset_id or current_accent_preset_id())
    light = _pick_accent_text_color(
        preset,
        (700, 900, 950),
        _LIGHT_REFERENCE_SURFACE,
    )
    dark = _pick_accent_text_color(
        preset,
        (300, 200, 100, 50),
        _DARK_REFERENCE_SURFACE,
    )
    return light, dark


def get_semantic_text_color_pair(
    role: SemanticColorRole,
    *,
    preset_id: AccentPresetId | str | None = None,
) -> tuple[QColor, QColor]:
    """返回指定颜色角色的亮暗主题前景色。

    Args:
        role: 页面引导或状态语义角色。
        preset_id: ``accent`` 角色使用的强调色预设。

    Returns:
        ``(light, dark)`` 主题色对。
    """
    if role == "accent":
        return get_accent_text_color_pair(preset_id)
    if role == "info":
        return QColor(_INFO_TEXT_PAIR[0]), QColor(_INFO_TEXT_PAIR[1])
    if role == "neutral":
        return QColor(_NEUTRAL_TEXT_PAIR[0]), QColor(_NEUTRAL_TEXT_PAIR[1])

    system_color = {
        "success": FluentSystemColor.SUCCESS_FOREGROUND,
        "caution": FluentSystemColor.CAUTION_FOREGROUND,
        "critical": FluentSystemColor.CRITICAL_FOREGROUND,
    }[role]
    return system_color.color(Theme.LIGHT), system_color.color(Theme.DARK)


def resolve_semantic_text_color(
    role: SemanticColorRole,
    *,
    preset_id: AccentPresetId | str | None = None,
) -> QColor:
    """按当前实际深浅主题解析颜色角色。"""
    light, dark = get_semantic_text_color_pair(role, preset_id=preset_id)
    return QColor(dark if isDarkTheme() else light)


__all__ = [
    "SemanticColorRole",
    "get_accent_text_color_pair",
    "get_semantic_text_color_pair",
    "resolve_semantic_text_color",
]
