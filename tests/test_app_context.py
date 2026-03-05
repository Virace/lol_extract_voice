from pathlib import Path

import pytest

import lol_audio_unpack as app_pkg
from lol_audio_unpack import setup_app
from lol_audio_unpack.app_context import (
    AppContext,
    OperationOptions,
    create_app_context,
    initialize_context_from_env,
)

pytestmark = pytest.mark.unit

DEFAULT_MAX_WORKERS = 4


def _write_env_file(env_dir: Path, game_path: Path, output_path: Path) -> None:
    (env_dir / ".lol.env").write_text(
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


def test_initialize_context_from_env_builds_typed_context(tmp_path: Path) -> None:
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)

    game_path = tmp_path / "game"
    output_path = tmp_path / "output"
    _write_env_file(env_dir, game_path, output_path)

    app_context = initialize_context_from_env(
        env_path=env_dir,
        cli_overrides={"WITH_BP_VO": True},
    )

    assert isinstance(app_context, AppContext)
    assert app_context.config.game_path == game_path
    assert app_context.config.output_path == output_path
    assert app_context.config.with_bp_vo is True
    assert app_context.paths.audio_path == output_path / "audios"
    assert app_context.paths.manifest_path == output_path / "manifest"


def test_create_app_context_applies_cli_overrides(tmp_path: Path) -> None:
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)

    game_path = tmp_path / "game"
    output_path = tmp_path / "output"
    _write_env_file(env_dir, game_path, output_path)

    app_context = create_app_context(
        env_path=env_dir,
        cli_overrides={"EXCLUDE_TYPE": "VO", "GROUP_BY_TYPE": True},
    )

    assert isinstance(app_context, AppContext)
    assert app_context.config.group_by_type is True
    assert app_context.config.exclude_types == ("VO",)
    assert set(app_context.config.include_types) == {"SFX", "MUSIC"}


def test_setup_app_returns_context_with_cli_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)

    game_path = tmp_path / "game"
    output_path = tmp_path / "output"
    _write_env_file(env_dir, game_path, output_path)

    monkeypatch.setattr(app_pkg.logger, "add", lambda *args, **kwargs: 1)
    app_context = setup_app(
        env_path=env_dir,
        dev_mode=True,
        log_level="INFO",
        cli_overrides={"EXCLUDE_TYPE": "VO", "GROUP_BY_TYPE": True},
    )

    assert isinstance(app_context, AppContext)
    assert app_context.config.dev_mode is True
    assert app_context.config.group_by_type is True
    assert app_context.config.exclude_types == ("VO",)
    assert set(app_context.config.include_types) == {"SFX", "MUSIC"}
    assert app_context.paths.log_path == output_path / "logs"


def test_operation_options_defaults() -> None:
    options = OperationOptions()

    assert options.max_workers == DEFAULT_MAX_WORKERS
    assert options.process_events is True
    assert options.integrate_data is False
