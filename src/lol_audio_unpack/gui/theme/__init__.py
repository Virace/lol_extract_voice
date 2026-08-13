"""GUI 壳模式、强调色预设与组件调色入口。"""

from lol_audio_unpack.gui.theme.presets import (
    DEFAULT_ACCENT_PRESET_ID,
    AccentPreset,
    AccentScale,
    ThemeProgressPalette,
    get_accent_preset,
    list_accent_presets,
    resolve_accent_preset_id,
    resolve_legacy_accent_preset,
)
from lol_audio_unpack.gui.theme.runtime import (
    apply_accent_preset,
    apply_shell_mode,
    current_accent_preset_id,
    resolve_progress_palette,
    shell_mode_from_theme,
)
from lol_audio_unpack.gui.theme.semantic import (
    SemanticColorRole,
    get_accent_text_color_pair,
    get_semantic_text_color_pair,
    resolve_semantic_text_color,
)

__all__ = [
    "AccentPreset",
    "AccentScale",
    "DEFAULT_ACCENT_PRESET_ID",
    "SemanticColorRole",
    "ThemeProgressPalette",
    "apply_accent_preset",
    "apply_shell_mode",
    "current_accent_preset_id",
    "get_accent_preset",
    "get_accent_text_color_pair",
    "get_semantic_text_color_pair",
    "list_accent_presets",
    "resolve_accent_preset_id",
    "resolve_legacy_accent_preset",
    "resolve_progress_palette",
    "resolve_semantic_text_color",
    "shell_mode_from_theme",
]
