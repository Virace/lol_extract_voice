"""测试关于页面中的品牌展示。"""

from __future__ import annotations

from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import QApplication

from lol_audio_unpack.gui.view.about_page import AboutPage


def test_about_page_displays_valid_svg_logo(qtbot) -> None:
    """关于页面应展示可用的 SVG logo。"""
    app = QApplication.instance() or QApplication([])
    page = AboutPage()
    qtbot.addWidget(page)
    app.processEvents()

    logo = page.findChild(QSvgWidget, "AboutPageLogo")

    assert logo is not None
    assert logo.renderer().isValid() is True
