"""GUI 配置持久化回归测试。"""

from __future__ import annotations

import configparser
from pathlib import Path

from lol_audio_unpack.config import ConfigSection, load_command_config
from lol_audio_unpack.gui.common.gui_config import GuiConfig
from lol_audio_unpack.gui.theme.presets import get_accent_preset

EXPECTED_WAV_WORKERS = 6
EXPECTED_WAV_TIMEOUT = 9
EXPECTED_WAV_RETRIES = 4
DEFAULT_PREVIEW_VOLUME_PERCENT = 10
EXPECTED_PREVIEW_VOLUME_PERCENT = 42


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


def test_gui_config_uses_defaults_when_project_ini_is_missing() -> None:
    """项目配置缺失时应使用 GUI 默认值。"""
    cfg = GuiConfig()

    cfg.load()

    assert cfg.preview_audio_volume_percent == DEFAULT_PREVIEW_VOLUME_PERCENT


def test_gui_config_load_reads_gui_section_from_project_ini(tmp_path: Path) -> None:
    """GUI 专有状态应从项目 INI 的 gui 分组读取。"""
    config_file = tmp_path / "config" / "lol-audio-unpack.ini"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        (
            "[gui]\n"
            "vgmstream_path = tools/vgmstream/vgmstream-cli.exe\n"
            "remote_snapshot_strategy = custom\n"
            "remote_snapshot_version = 16.12\n"
            "remote_snapshot_lcu_url = https://example.com/lcu.manifest\n"
            "remote_snapshot_game_url = https://example.com/game.manifest\n"
            "theme_mode = Dark\n"
            "accent_preset_id = purple\n"
            "page_smooth_scroll_enabled = true\n"
            "widget_smooth_scroll_enabled = true\n"
            "log_drawer_auto_collapse_enabled = false\n"
            "console_log_level = warning\n"
            "file_log_level = info\n"
            f"preview_audio_volume_percent = {EXPECTED_PREVIEW_VOLUME_PERCENT}\n"
            "preview_audio_output_device_key = device-a\n"
        ),
        encoding="utf-8",
    )

    cfg = GuiConfig()
    cfg._config_file = config_file
    cfg.load()

    assert cfg.vgmstream_path == "tools/vgmstream/vgmstream-cli.exe"
    assert cfg.remote_snapshot_strategy == "custom"
    assert cfg.snapshot_version == "16.12"
    assert cfg.snapshot_lcu_url == "https://example.com/lcu.manifest"
    assert cfg.snapshot_game_url == "https://example.com/game.manifest"
    assert cfg.theme_mode == "Dark"
    assert cfg.accent_preset_id == "purple"
    assert cfg.theme_color.lower() == get_accent_preset("purple").primary_hex.lower()
    assert cfg.page_smooth_scroll_enabled is True
    assert cfg.widget_smooth_scroll_enabled is True
    assert cfg.log_drawer_auto_collapse_enabled is False
    assert cfg.console_log_level == "WARNING"
    assert cfg.file_log_level == "INFO"
    assert cfg.preview_audio_volume_percent == EXPECTED_PREVIEW_VOLUME_PERCENT
    assert cfg.preview_audio_output_device_key == "device-a"


def test_gui_config_save_persists_gui_state_to_project_ini(tmp_path: Path) -> None:
    """保存 GUI 配置时应把 GUI 状态统一写入项目 INI。"""
    config_file = tmp_path / "config" / "lol-audio-unpack.ini"
    cfg = GuiConfig()
    cfg._config_file = config_file
    cfg.vgmstream_path = "tools/vgmstream/vgmstream-cli.exe"
    cfg.remote_snapshot_strategy = "custom"
    cfg.snapshot_version = "16.12"
    cfg.snapshot_lcu_url = "https://example.com/lcu.manifest"
    cfg.snapshot_game_url = "https://example.com/game.manifest"
    cfg.theme_mode = "Dark"
    cfg.accent_preset_id = "orange"
    cfg.page_smooth_scroll_enabled = True
    cfg.widget_smooth_scroll_enabled = True
    cfg.log_drawer_auto_collapse_enabled = False
    cfg.console_log_level = "WARNING"
    cfg.file_log_level = "INFO"
    cfg.preview_audio_volume_percent = EXPECTED_PREVIEW_VOLUME_PERCENT
    cfg.preview_audio_output_device_key = "device-a"

    cfg.save()

    reloaded = GuiConfig()
    reloaded._config_file = config_file
    reloaded.load()

    assert reloaded.vgmstream_path == "tools/vgmstream/vgmstream-cli.exe"
    assert reloaded.remote_snapshot_strategy == "custom"
    assert reloaded.snapshot_version == "16.12"
    assert reloaded.snapshot_lcu_url == "https://example.com/lcu.manifest"
    assert reloaded.snapshot_game_url == "https://example.com/game.manifest"
    assert reloaded.theme_mode == "Dark"
    assert reloaded.accent_preset_id == "orange"
    assert reloaded.theme_color.lower() == get_accent_preset("orange").primary_hex.lower()
    assert reloaded.page_smooth_scroll_enabled is True
    assert reloaded.widget_smooth_scroll_enabled is True
    assert reloaded.log_drawer_auto_collapse_enabled is False
    assert reloaded.console_log_level == "WARNING"
    assert reloaded.file_log_level == "INFO"
    assert reloaded.preview_audio_volume_percent == EXPECTED_PREVIEW_VOLUME_PERCENT
    assert reloaded.preview_audio_output_device_key == "device-a"


def test_gui_config_save_theme_preferences_updates_project_ini_only(tmp_path: Path) -> None:
    """主题快速保存只应更新项目 INI 的主题字段并保留其他 GUI 字段。"""
    config_file = tmp_path / "config" / "lol-audio-unpack.ini"
    cfg = GuiConfig()
    cfg._config_file = config_file
    cfg.preview_audio_volume_percent = EXPECTED_PREVIEW_VOLUME_PERCENT
    cfg.save()
    cfg.theme_mode = "Light"
    cfg.accent_preset_id = "blue"

    cfg.save_theme_preferences()

    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(config_file, encoding="utf-8")
    assert parser[ConfigSection.GUI]["theme_mode"] == "Light"
    assert parser[ConfigSection.GUI]["accent_preset_id"] == "blue"
    assert parser[ConfigSection.GUI]["preview_audio_volume_percent"] == str(EXPECTED_PREVIEW_VOLUME_PERCENT)
    assert "theme_color" not in parser[ConfigSection.GUI]
