"""验证主题预设兼容映射与语义色对比度。"""

from PySide6.QtGui import QColor

from lol_audio_unpack.gui.theme.presets import (
    DEFAULT_ACCENT_PRESET_ID,
    list_accent_presets,
    resolve_legacy_accent_preset,
)
from lol_audio_unpack.gui.theme.semantic import (
    get_accent_text_color_pair,
    get_semantic_text_color_pair,
)

_SRGB_LINEAR_THRESHOLD = 0.04045
_BODY_TEXT_CONTRAST_TARGET = 4.5


def _linear_channel(value: float) -> float:
    """把 sRGB 通道转换为对比度计算所需的线性值。"""
    return value / 12.92 if value <= _SRGB_LINEAR_THRESHOLD else ((value + 0.055) / 1.055) ** 2.4


def _relative_luminance(color: QColor) -> float:
    """计算颜色的 WCAG 相对亮度。"""
    return sum(
        weight * _linear_channel(channel)
        for weight, channel in zip(
            (0.2126, 0.7152, 0.0722),
            (color.redF(), color.greenF(), color.blueF()),
            strict=True,
        )
    )


def _contrast_ratio(foreground: QColor, background: QColor) -> float:
    """计算前景与背景的 WCAG 对比度。"""
    lighter, darker = sorted(
        (_relative_luminance(foreground), _relative_luminance(background)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


def test_resolve_legacy_accent_preset_falls_back_to_default_for_unknown_color() -> None:
    """无法识别的旧颜色应回退到默认预设。"""
    assert resolve_legacy_accent_preset("#009faa") == DEFAULT_ACCENT_PRESET_ID


def test_accent_guidance_text_meets_contrast_target_for_every_preset() -> None:
    """每种强调色的页面引导文字都应满足正文对比度目标。"""
    for preset in list_accent_presets():
        light, dark = get_accent_text_color_pair(preset.id)

        assert _contrast_ratio(light, QColor("#FFFFFF")) >= _BODY_TEXT_CONTRAST_TARGET
        assert _contrast_ratio(dark, QColor("#111111")) >= _BODY_TEXT_CONTRAST_TARGET


def test_status_semantic_colors_do_not_follow_accent_preset() -> None:
    """成功等状态色应保持稳定，不随用户选择的强调色漂移。"""
    assert get_semantic_text_color_pair("success", preset_id="blue") == (
        get_semantic_text_color_pair("success", preset_id="orange")
    )
