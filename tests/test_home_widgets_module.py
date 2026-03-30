"""首页展示组件模块的基本可用性测试。"""

from __future__ import annotations

from lol_audio_unpack.gui.view.home.widgets import ClickableCard, QuickOpenRow


def test_home_widgets_module_exports_display_components() -> None:
    assert ClickableCard is not None
    assert QuickOpenRow is not None
