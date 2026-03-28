"""测试顶层页面共用的布局 token。"""

from __future__ import annotations

import importlib

import pytest
from PySide6.QtWidgets import QApplication, QLayout

from lol_audio_unpack.gui.common import GuiConfig
from lol_audio_unpack.gui.view.about_page import AboutPage
from lol_audio_unpack.gui.view.execution_page import ExecutionPage
from lol_audio_unpack.gui.view.home_page import HomePage
from lol_audio_unpack.gui.view.overview_page import OverviewPage
from lol_audio_unpack.gui.view.setting_page import SettingPage


def _load_style_module():
    """加载页面布局 token 模块。"""
    try:
        return importlib.import_module("lol_audio_unpack.gui.common.style")
    except ModuleNotFoundError as exc:  # pragma: no cover - red phase guard
        pytest.fail(f"缺少页面布局 token 模块: {exc}")


def _layout_margins(layout: QLayout) -> tuple[int, int, int, int]:
    """返回布局当前的边距四元组。"""
    margins = layout.contentsMargins()
    return (margins.left(), margins.top(), margins.right(), margins.bottom())


def test_style_module_exposes_shared_page_margin_tokens() -> None:
    """页面布局 token 应集中定义在单独的 style 模块中。"""
    style_module = _load_style_module()

    assert getattr(style_module, "PAGE_CONTENT_MARGINS", None) == (24, 24, 24, 24)


def test_navigation_pages_use_shared_page_margin_tokens(qtbot, monkeypatch) -> None:
    """导航中的顶层页面应使用统一的外层页边距 token。"""
    style_module = _load_style_module()
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(HomePage, "_start_background_check", lambda self: None)

    home_page = HomePage(GuiConfig(dev_mode=True))
    execution_page = ExecutionPage()
    overview_page = OverviewPage()
    setting_page = SettingPage()
    about_page = AboutPage()

    for page in (home_page, execution_page, overview_page, setting_page, about_page):
        qtbot.addWidget(page)
    app.processEvents()

    expected_margins = style_module.PAGE_CONTENT_MARGINS

    assert _layout_margins(home_page.view.layout()) == expected_margins
    assert _layout_margins(execution_page.view.layout()) == expected_margins
    assert _layout_margins(overview_page.layout()) == expected_margins
    assert _layout_margins(setting_page.view.layout()) == expected_margins
    assert _layout_margins(about_page.view.layout()) == expected_margins
