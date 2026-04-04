"""设置页子面板模块可用性测试。"""

from __future__ import annotations

from lol_audio_unpack.gui.view.settings.appearance_panel import AppearancePanel
from lol_audio_unpack.gui.view.settings.source_mode_panel import SourceModePanel
from lol_audio_unpack.gui.view.settings.tool_path_panel import (
    BaseSettingsPanel,
    ToolPathPanel,
)


def test_setting_panels_modules_export_panel_classes() -> None:
    assert SourceModePanel is not None
    assert BaseSettingsPanel is not None
    assert ToolPathPanel is not None
    assert AppearancePanel is not None
