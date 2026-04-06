"""GUI 配置中的 WAV 默认值回归测试。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

from lol_audio_unpack.config import load_command_config
from lol_audio_unpack.gui.common.gui_config import GuiConfig
from lol_audio_unpack.gui.theme.presets import get_accent_preset

EXPECTED_WAV_WORKERS = 6
EXPECTED_WAV_TIMEOUT = 9
EXPECTED_WAV_RETRIES = 4


def test_gui_config_load_reads_wav_command_defaults(tmp_path: Path) -> None:
    """应从标准 INI 的 wav 分组读取 WAV 相关默认值。"""
    config_file = tmp_path / "lol-audio-unpack.ini"
    config_file.write_text(
        (
            "[app]\n"
            "game_path = ./game\n"
            "\n"
            "[wav]\n"
            "enable = true\n"
            f"wav_workers = {EXPECTED_WAV_WORKERS}\n"
            f"wav_timeout = {EXPECTED_WAV_TIMEOUT}\n"
            f"wav_retries = {EXPECTED_WAV_RETRIES}\n"
            "wav_format = float\n"
        ),
        encoding="utf-8",
    )

    cfg = GuiConfig()
    cfg._config_file = config_file

    cfg.load()

    assert cfg.wav_enabled is True
    assert cfg.wav_workers == EXPECTED_WAV_WORKERS
    assert cfg.wav_timeout == EXPECTED_WAV_TIMEOUT
    assert cfg.wav_retries == EXPECTED_WAV_RETRIES
    assert cfg.wav_format == "float"


def test_gui_config_save_updates_wav_group_enable_and_tuning(tmp_path: Path) -> None:
    """保存 GUI 配置时应把开关与参数统一写回 wav 分组。"""
    config_file = tmp_path / "lol-audio-unpack.ini"
    config_file.write_text(
        (
            "[app]\n"
            "game_path = ./game\n"
            "\n"
            "[extract]\n"
            "wav = true\n"
            "\n"
            "[wav]\n"
            "enable = true\n"
            "wav_workers = 2\n"
            "wav_timeout = 5\n"
            "wav_retries = 3\n"
            "wav_format = auto\n"
        ),
        encoding="utf-8",
    )

    cfg = GuiConfig()
    cfg._config_file = config_file
    cfg.load()
    cfg.wav_workers = 8
    cfg.wav_timeout = 11
    cfg.wav_retries = 5

    cfg.save()

    assert load_command_config(config_file, command="wav") == {
        "wav": True,
        "wav_workers": 8,
        "wav_timeout": 11,
        "wav_retries": 5,
        "wav_format": "auto",
    }
    assert load_command_config(config_file, command="extract") == {}
    assert "wav = true" not in config_file.read_text(encoding="utf-8")


def test_gui_config_load_migrates_legacy_theme_color_to_accent_preset(tmp_path: Path) -> None:
    """旧主题色应迁移到固定 accent preset。"""
    settings_file = tmp_path / "gui-settings.ini"
    legacy_settings = QSettings(str(settings_file), QSettings.Format.IniFormat)
    legacy_settings.setValue("theme_mode", "Dark")
    legacy_settings.setValue("theme_color", get_accent_preset("purple").primary_hex)
    legacy_settings.sync()

    cfg = GuiConfig()
    cfg._qs = QSettings(str(settings_file), QSettings.Format.IniFormat)

    cfg.load()

    assert cfg.theme_mode == "Dark"
    assert cfg.accent_preset_id == "purple"
    assert cfg.theme_color.lower() == get_accent_preset("purple").primary_hex.lower()


def test_gui_config_save_persists_theme_mode_and_accent_preset(tmp_path: Path) -> None:
    """新主题配置应写回壳模式与 accent preset。"""
    config_file = tmp_path / "lol-audio-unpack.ini"
    settings_file = tmp_path / "gui-settings.ini"

    cfg = GuiConfig()
    cfg._config_file = config_file
    cfg._qs = QSettings(str(settings_file), QSettings.Format.IniFormat)
    cfg.theme_mode = "Dark"
    cfg.accent_preset_id = "orange"

    cfg.save_theme_preferences()
    cfg._qs.sync()

    reloaded = GuiConfig()
    reloaded._config_file = config_file
    reloaded._qs = QSettings(str(settings_file), QSettings.Format.IniFormat)
    reloaded.load()

    assert reloaded.theme_mode == "Dark"
    assert reloaded.accent_preset_id == "orange"
    assert reloaded.theme_color.lower() == get_accent_preset("orange").primary_hex.lower()


def test_gui_config_save_theme_preferences_stops_writing_legacy_theme_color(tmp_path: Path) -> None:
    """新主题配置不应继续把 legacy theme_color 作为主写回字段。"""
    settings_file = tmp_path / "gui-settings.ini"

    cfg = GuiConfig()
    cfg._qs = QSettings(str(settings_file), QSettings.Format.IniFormat)
    cfg.theme_mode = "Light"
    cfg.accent_preset_id = "blue"

    cfg.save_theme_preferences()
    cfg._qs.sync()

    stored = QSettings(str(settings_file), QSettings.Format.IniFormat)
    assert stored.value("theme_mode") == "Light"
    assert stored.value("accent_preset_id") == "blue"
    assert stored.value("theme_color") is None
