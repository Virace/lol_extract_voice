"""GUI 配置中的 WAV 默认值回归测试。"""

from __future__ import annotations

from pathlib import Path

from lol_audio_unpack.config import load_command_config
from lol_audio_unpack.gui.common.gui_config import GuiConfig

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
