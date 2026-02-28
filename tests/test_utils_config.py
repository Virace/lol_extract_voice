import os
from pathlib import Path

import pytest

from lol_audio_unpack.utils.config import Config


@pytest.fixture(autouse=True)
def reset_config_singleton():
    Config._instance = None
    yield
    Config._instance = None


@pytest.fixture(autouse=True)
def disable_logger_init(monkeypatch):
    monkeypatch.setattr(Config, "logger_init", lambda self: None)


def _clear_lol_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith("LOL_"):
            monkeypatch.delenv(key, raising=False)


def test_config_loads_defaults_and_derived_paths(monkeypatch, tmp_path):
    _clear_lol_env(monkeypatch)
    game = tmp_path / "game"
    output = tmp_path / "output"

    cfg = Config(
        GAME_PATH=str(game),
        OUTPUT_PATH=str(output),
        DEBUG="20",
    )

    assert cfg.get("GAME_PATH") == game
    assert cfg.get("OUTPUT_PATH") == output
    assert cfg.get("AUDIO_PATH") == output / "audios"
    assert cfg.get("MANIFEST_PATH") == output / "manifest"

    include_type = [item.strip() for item in cfg.get("INCLUDE_TYPE")]
    assert include_type == ["VO", "SFX", "MUSIC"]


def test_config_environment_variable_priority(monkeypatch, tmp_path):
    _clear_lol_env(monkeypatch)
    game = tmp_path / "game"
    output = tmp_path / "output"

    monkeypatch.setenv("LOL_GAME_PATH", str(game))
    monkeypatch.setenv("LOL_OUTPUT_PATH", str(output))
    monkeypatch.setenv("LOL_GAME_REGION", "ko_KR")
    monkeypatch.setenv("LOL_DEBUG", "20")

    cfg = Config()
    assert cfg.get("GAME_REGION") == "ko_KR"


def test_config_kwargs_higher_priority_than_environment(monkeypatch, tmp_path):
    _clear_lol_env(monkeypatch)
    game = tmp_path / "game"
    output = tmp_path / "output"

    monkeypatch.setenv("LOL_GAME_REGION", "ko_KR")

    cfg = Config(
        GAME_PATH=str(game),
        OUTPUT_PATH=str(output),
        GAME_REGION="zh_CN",
        DEBUG="20",
    )
    assert cfg.get("GAME_REGION") == "zh_CN"


def test_config_normalizes_en_us_to_default(monkeypatch, tmp_path):
    _clear_lol_env(monkeypatch)
    game = tmp_path / "game"
    output = tmp_path / "output"

    cfg = Config(
        GAME_PATH=str(game),
        OUTPUT_PATH=str(output),
        GAME_REGION="en_US",
        DEBUG="20",
    )
    assert cfg.get("GAME_REGION") == "default"


def test_config_missing_required_params_raises(monkeypatch):
    _clear_lol_env(monkeypatch)
    with pytest.raises(ValueError, match="缺少必要参数"):
        Config(DEBUG="20")
