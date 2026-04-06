"""GUI 资源边界的结构性回归测试。"""

from pathlib import Path

TARGETS = (
    Path("src/lol_audio_unpack/gui/window.py"),
    Path("src/lol_audio_unpack/gui/view/about_page.py"),
    Path("src/lol_audio_unpack/gui/view/settings/appearance_panel.py"),
    Path("src/lol_audio_unpack/gui/components/global_progress_strip.py"),
)

FORBIDDEN_SUBSTRINGS = (
    "Path(__file__)",
    ' / "assets"',
    ' / "icon"',
    ' / "qr"',
    "BILIBILI_ICON_PATH",
    "QR_CODE_ASSET_DIR",
    "AccentPresetIcon",
    "ProgressActionIcon",
    "AboutCustomIcon",
    "load_app_icon",
)


def test_resource_consumers_do_not_embed_local_paths_or_enums() -> None:
    """页面与组件层不应重新嵌入资源路径知识。"""
    for path in TARGETS:
        source = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_SUBSTRINGS:
            assert forbidden not in source, f"{path} still contains {forbidden}"
