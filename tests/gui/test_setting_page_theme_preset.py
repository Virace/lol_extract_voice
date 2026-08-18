"""设置页壳模式与固定 accent preset 回归测试。"""

from __future__ import annotations

import configparser
from pathlib import Path

from qfluentwidgets import Theme, qconfig

from lol_audio_unpack.gui.view.setting_page import SettingPage


def _use_temp_settings(page: SettingPage, tmp_path: Path) -> None:
    """把页面配置切到临时项目 INI 文件。"""
    page.config._config_file = tmp_path / "config" / "lol-audio-unpack.ini"


def test_setting_page_round_trips_accent_preset(qtbot, tmp_path: Path) -> None:
    """设置页应回填已保存主题，并把后续选择写回配置。"""
    page = SettingPage()
    qtbot.addWidget(page)
    _use_temp_settings(page, tmp_path)
    page.config.theme_mode = "Dark"
    page.config.accent_preset_id = "orange"

    page._apply_theme_from_config()

    assert page.accentPresetCard.value() == "orange"
    assert qconfig.themeMode.value == Theme.DARK

    page.accentPresetCard.comboBox.setCurrentText("绿色")
    qtbot.wait(0)

    assert page.config.accent_preset_id == "green"
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(page.config._config_file, encoding="utf-8")
    assert parser["gui"]["accent_preset_id"] == "green"
