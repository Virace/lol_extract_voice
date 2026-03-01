import os
from pathlib import Path

import pytest

from lol_audio_unpack.utils.config import Config, ConfigValidationError

pytestmark = pytest.mark.unit


def _write_env_file(env_dir: Path, filename: str, game_path: Path, output_path: Path) -> None:
    (env_dir / filename).write_text(
        "\n".join(
            [
                f'LOL_GAME_PATH="{game_path}"',
                f'LOL_OUTPUT_PATH="{output_path}"',
                'LOL_GAME_REGION="zh_CN"',
                'LOL_EXCLUDE_TYPE="SFX,MUSIC"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_config_default_mode_uses_dot_env_only(tmp_path):
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)

    game_prod = tmp_path / "game_prod"
    output_prod = tmp_path / "output_prod"
    game_dev = tmp_path / "game_dev"
    output_dev = tmp_path / "output_dev"

    _write_env_file(env_dir, ".lol.env", game_prod, output_prod)
    _write_env_file(env_dir, ".lol.env.dev", game_dev, output_dev)

    cfg = Config(env_path=env_dir, force_reload=True, dev_mode=False)

    assert cfg.GAME_PATH == game_prod
    assert cfg.OUTPUT_PATH == output_prod
    assert cfg.is_dev_mode() is False


def test_config_dev_mode_prefers_dot_env_dev(tmp_path):
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)

    game_prod = tmp_path / "game_prod"
    output_prod = tmp_path / "output_prod"
    game_dev = tmp_path / "game_dev"
    output_dev = tmp_path / "output_dev"

    _write_env_file(env_dir, ".lol.env", game_prod, output_prod)
    _write_env_file(env_dir, ".lol.env.dev", game_dev, output_dev)

    cfg = Config(env_path=env_dir, force_reload=True, dev_mode=True)

    assert cfg.GAME_PATH == game_dev
    assert cfg.OUTPUT_PATH == output_dev
    assert cfg.is_dev_mode() is True


def test_config_dev_mode_fallbacks_to_dot_env_when_dev_missing(tmp_path):
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)

    game_prod = tmp_path / "game_prod"
    output_prod = tmp_path / "output_prod"

    _write_env_file(env_dir, ".lol.env", game_prod, output_prod)

    cfg = Config(env_path=env_dir, force_reload=True, dev_mode=True)

    assert cfg.GAME_PATH == game_prod
    assert cfg.OUTPUT_PATH == output_prod
    assert cfg.is_dev_mode() is True


def test_config_non_dev_mode_does_not_read_dot_env_dev_alone(tmp_path):
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)

    game_dev = tmp_path / "game_dev"
    output_dev = tmp_path / "output_dev"

    _write_env_file(env_dir, ".lol.env.dev", game_dev, output_dev)

    with pytest.raises(ConfigValidationError):
        Config(env_path=env_dir, force_reload=True, dev_mode=False)

    assert os.environ.get("LOL_GAME_PATH") is None


def test_config_system_env_overrides_dotenv(tmp_path, monkeypatch):
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)

    game_dotenv = tmp_path / "game_dotenv"
    output_dotenv = tmp_path / "output_dotenv"
    game_env = tmp_path / "game_env"
    output_env = tmp_path / "output_env"

    _write_env_file(env_dir, ".lol.env", game_dotenv, output_dotenv)
    monkeypatch.setenv("LOL_GAME_PATH", str(game_env))
    monkeypatch.setenv("LOL_OUTPUT_PATH", str(output_env))

    cfg = Config(env_path=env_dir, force_reload=True, dev_mode=False)

    assert cfg.GAME_PATH == game_env
    assert cfg.OUTPUT_PATH == output_env
    assert cfg.sources["GAME_PATH"] == "env"
    assert cfg.sources["OUTPUT_PATH"] == "env"


def test_config_unknown_lol_keys_are_ignored(tmp_path, monkeypatch):
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)

    game_path = tmp_path / "game"
    output_path = tmp_path / "output"

    _write_env_file(env_dir, ".lol.env", game_path, output_path)
    monkeypatch.setenv("LOL_UNKNOWN_KEY", "unexpected")

    cfg = Config(env_path=env_dir, force_reload=True, dev_mode=False)

    assert "UNKNOWN_KEY" not in cfg.as_dict()


def test_config_missing_required_raises_fast(tmp_path):
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)

    with pytest.raises(ConfigValidationError):
        Config(env_path=env_dir, force_reload=True, dev_mode=False)
