"""验证旧主题配置向固定预设的兼容映射。"""

from lol_audio_unpack.gui.theme.presets import (
    DEFAULT_ACCENT_PRESET_ID,
    resolve_legacy_accent_preset,
)


def test_resolve_legacy_accent_preset_falls_back_to_default_for_unknown_color() -> None:
    """无法识别的旧颜色应回退到默认预设。"""
    assert resolve_legacy_accent_preset("#009faa") == DEFAULT_ACCENT_PRESET_ID
