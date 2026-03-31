"""Switch 组件字体兼容性测试。"""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QWidget
from qfluentwidgets import FluentIcon as FIF

from lol_audio_unpack.gui.components.log_drawer import GlobalLogDrawer
from lol_audio_unpack.gui.view.settings.cards import (
    LocalizedSwitchSettingCard,
    SmoothScrollSettingCard,
)


def test_localized_switch_setting_card_uses_font_with_positive_point_size(qtbot) -> None:
    app = QApplication.instance()
    original_font = QFont(app.font())
    pixel_font = QFont("Microsoft YaHei")
    pixel_font.setPixelSize(14)

    try:
        app.setFont(pixel_font)
        card = LocalizedSwitchSettingCard(FIF.INFO, "标题", "说明")
        qtbot.addWidget(card)

        assert card.switchButton.font().pointSizeF() > 0
        assert card.switchButton.indicator.font().pointSizeF() > 0
        assert "font:" in str(card.switchButton.property("lightCustomQss") or "")
        assert "pt" in str(card.switchButton.property("lightCustomQss") or "")
    finally:
        app.setFont(original_font)


def test_smooth_scroll_setting_card_switches_use_font_with_positive_point_size(qtbot) -> None:
    app = QApplication.instance()
    original_font = QFont(app.font())
    pixel_font = QFont("Microsoft YaHei")
    pixel_font.setPixelSize(14)

    try:
        app.setFont(pixel_font)
        card = SmoothScrollSettingCard()
        qtbot.addWidget(card)

        assert card.pageSwitchButton.font().pointSizeF() > 0
        assert card.pageSwitchButton.indicator.font().pointSizeF() > 0
        assert "pt" in str(card.pageSwitchButton.property("lightCustomQss") or "")
        assert card.widgetSwitchButton.font().pointSizeF() > 0
        assert card.widgetSwitchButton.indicator.font().pointSizeF() > 0
        assert "pt" in str(card.widgetSwitchButton.property("lightCustomQss") or "")
    finally:
        app.setFont(original_font)


def test_log_drawer_follow_scroll_switch_uses_font_with_positive_point_size(qtbot) -> None:
    app = QApplication.instance()
    original_font = QFont(app.font())
    pixel_font = QFont("Microsoft YaHei")
    pixel_font.setPixelSize(14)

    try:
        app.setFont(pixel_font)
        host = QWidget()
        host.resize(1280, 720)
        qtbot.addWidget(host)
        drawer = GlobalLogDrawer(host)

        assert drawer._follow_scroll_switch.font().pointSizeF() > 0
        assert drawer._follow_scroll_switch.indicator.font().pointSizeF() > 0
        assert "pt" in str(drawer._follow_scroll_switch.property("lightCustomQss") or "")
    finally:
        app.setFont(original_font)
