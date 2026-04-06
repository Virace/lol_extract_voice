"""设置页壳模式与固定 accent preset 回归测试。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings
from qfluentwidgets import Theme, qconfig
from qfluentwidgets.common.icon import writeSvg

from lol_audio_unpack.gui.resources import assets
from lol_audio_unpack.gui.theme.presets import get_accent_preset
from lol_audio_unpack.gui.view.setting_page import SettingPage

EXPECTED_ICON_CHANNEL_TOLERANCE = 8


def _use_temp_settings(page: SettingPage, tmp_path: Path) -> None:
    """把页面配置切到临时 QSettings 文件。"""
    settings_file = tmp_path / "gui-settings.ini"
    page.config._qs = QSettings(str(settings_file), QSettings.Format.IniFormat)
    page.config._qs.clear()
    page.config._qs.sync()


def test_setting_page_applies_saved_accent_preset_to_selector(qtbot, tmp_path: Path) -> None:
    """设置页应把已保存的 accent preset 回填到下拉框。"""
    page = SettingPage()
    qtbot.addWidget(page)
    _use_temp_settings(page, tmp_path)
    page.config.theme_mode = "Dark"
    page.config.accent_preset_id = "orange"

    page._apply_theme_from_config()

    assert page.accentPresetCard.value() == "orange"
    assert qconfig.themeMode.value == Theme.DARK
    assert qconfig.themeColor.value.name().lower() == get_accent_preset("orange").primary_hex.lower()


def test_setting_page_persists_selected_accent_preset(qtbot, tmp_path: Path) -> None:
    """切换设置页 accent preset 后应立即写回配置。"""
    page = SettingPage()
    qtbot.addWidget(page)
    _use_temp_settings(page, tmp_path)

    page.accentPresetCard.comboBox.setCurrentText("绿色")
    qtbot.wait(0)

    assert page.config.accent_preset_id == "green"
    assert page.config._qs.value("accent_preset_id") == "green"
    assert qconfig.themeColor.value.name().lower() == get_accent_preset("green").primary_hex.lower()


def test_setting_page_accent_preset_items_show_color_icons(qtbot) -> None:
    """固定 accent preset 下拉项应显示颜色图标，避免纯文本难以辨认。"""
    page = SettingPage()
    qtbot.addWidget(page)

    for index in range(page.accentPresetCard.comboBox.count()):
        assert page.accentPresetCard.comboBox.itemIcon(index).isNull() is False


def test_setting_page_accent_preset_icon_uses_matching_item_color(qtbot) -> None:
    """下拉项图标应直接使用对应 preset 颜色，而不是模板默认色。"""
    page = SettingPage()
    qtbot.addWidget(page)

    icon = page.accentPresetCard.comboBox.itemIcon(0)
    pixmap = icon.pixmap(16, 16)
    center = pixmap.toImage().pixelColor(8, 8)
    expected = get_accent_preset("purple").primary_color

    assert abs(center.red() - expected.red()) <= EXPECTED_ICON_CHANNEL_TOLERANCE
    assert abs(center.green() - expected.green()) <= EXPECTED_ICON_CHANNEL_TOLERANCE
    assert abs(center.blue() - expected.blue()) <= EXPECTED_ICON_CHANNEL_TOLERANCE


def test_accent_dot_icon_svg_can_be_recolored_by_colored_icon() -> None:
    """accent dot SVG 模板应允许 ColoredFluentIcon 改写 fill 颜色。"""
    svg = writeSvg(assets.icons.DOT.path(), fill="#4C83D2")

    assert "<path" in svg
    assert 'fill="#4C83D2"' in svg


def test_accent_dot_icon_uses_circle_solid_template() -> None:
    """accent preset 图标应复用现成的 circle-solid-full.svg 模板。"""
    assert assets.icons.DOT.path().endswith("circle-solid-full.svg")


def test_appearance_panel_does_not_keep_local_accent_icon_enum() -> None:
    """个性化面板不应继续保留本地资源枚举。"""
    source = Path("src/lol_audio_unpack/gui/view/settings/appearance_panel.py").read_text(encoding="utf-8")

    assert "AccentPresetIcon" not in source
