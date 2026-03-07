from pathlib import Path
from types import SimpleNamespace

import pytest

import lol_audio_unpack as app_pkg
import lol_audio_unpack.app_context as app_context_module
from lol_audio_unpack import setup_app
from lol_audio_unpack.app_context import (
    AppContext,
    OperationOptions,
    SourceMode,
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
    assert not app_context.paths.audio_path.exists()
    assert not app_context.paths.manifest_path.exists()


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


def test_create_app_context_builds_remote_snapshot_config(tmp_path: Path) -> None:
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    output_path = tmp_path / "output"
    (env_dir / ".lol.env").write_text(
        f'LOL_OUTPUT_PATH="{output_path}"\n',
        encoding="utf-8",
    )

    app_context = create_app_context(
        env_path=env_dir,
        cli_overrides={
            "SOURCE_MODE": "remote_snapshot",
            "REMOTE_VERSION": "16.5.751.1533",
            "REMOTE_LCU_MANIFEST_URL": "https://example.com/lcu.manifest",
            "REMOTE_GAME_MANIFEST_URL": "https://example.com/game.manifest",
        },
    )

    assert app_context.config.source_mode is SourceMode.REMOTE_SNAPSHOT
    assert app_context.config.cleanup_remote is True
    assert app_context.config.game_path == output_path / "_prepared_game"
    assert app_context.config.remote_snapshot is not None
    assert app_context.config.remote_snapshot.version == "16.5"
    assert app_context.config.remote_snapshot.lcu_manifest_url == "https://example.com/lcu.manifest"
    assert app_context.config.remote_snapshot.game_manifest_url == "https://example.com/game.manifest"


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
    assert app_context.paths.log_path.is_dir()


def test_setup_app_falls_back_when_enqueue_logging_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)

    game_path = tmp_path / "game"
    output_path = tmp_path / "output"
    _write_env_file(env_dir, game_path, output_path)

    calls = []

    def fake_add(*args, **kwargs):
        calls.append(kwargs)
        if kwargs.get("enqueue") is True:
            raise PermissionError("no semaphore")
        return 1

    monkeypatch.setattr(app_pkg.logger, "add", fake_add)

    app_context = setup_app(
        env_path=env_dir,
        dev_mode=False,
        log_level="INFO",
    )

    assert isinstance(app_context, AppContext)
    assert calls[0]["enqueue"] is True
    assert calls[1]["enqueue"] is False
    assert calls[2]["enqueue"] is True
    assert calls[3]["enqueue"] is False


def test_create_app_context_accepts_cleanup_remote_override(tmp_path: Path) -> None:
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    output_path = tmp_path / "output"
    (env_dir / ".lol.env").write_text(
        f'LOL_OUTPUT_PATH="{output_path}"\n',
        encoding="utf-8",
    )

    app_context = create_app_context(
        env_path=env_dir,
        cli_overrides={
            "SOURCE_MODE": "remote_snapshot",
            "CLEANUP_REMOTE": False,
            "REMOTE_VERSION": "16.5.751.1533",
            "REMOTE_LCU_MANIFEST_URL": "https://example.com/lcu.manifest",
            "REMOTE_GAME_MANIFEST_URL": "https://example.com/game.manifest",
        },
    )

    assert app_context.config.cleanup_remote is False


def test_create_app_context_auto_resolves_remote_snapshot_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    output_path = tmp_path / "output"
    (env_dir / ".lol.env").write_text(
        f'LOL_OUTPUT_PATH="{output_path}"\n',
        encoding="utf-8",
    )

    captured: dict[str, str] = {}

    class FakeLeagueManifestResolver:
        def resolve_manifest_pair(self, region: str, **_: object):
            captured["region"] = region
            return SimpleNamespace(
                version="16.5.751.1533",
                lcu=SimpleNamespace(url="https://example.com/live.lcu.manifest"),
                game=SimpleNamespace(url="https://example.com/live.game.manifest"),
            )

    monkeypatch.setattr(app_context_module, "LeagueManifestResolver", FakeLeagueManifestResolver)

    app_context = create_app_context(
        env_path=env_dir,
        cli_overrides={
            "SOURCE_MODE": "remote_snapshot",
        },
    )

    assert captured["region"] == "EUW"
    assert app_context.config.remote_snapshot is not None
    assert app_context.config.remote_snapshot.version == "16.5"
    assert app_context.config.remote_snapshot.lcu_manifest_url == "https://example.com/live.lcu.manifest"
    assert app_context.config.remote_snapshot.game_manifest_url == "https://example.com/live.game.manifest"


def test_create_app_context_auto_resolves_remote_snapshot_config_with_live_region_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    output_path = tmp_path / "output"
    (env_dir / ".lol.env").write_text(
        f'LOL_OUTPUT_PATH="{output_path}"\n',
        encoding="utf-8",
    )

    captured: dict[str, str] = {}

    class FakeLeagueManifestResolver:
        def resolve_manifest_pair(self, region: str, **_: object):
            captured["region"] = region
            return SimpleNamespace(
                version="16.5.751.1533",
                lcu=SimpleNamespace(url="https://example.com/live.lcu.manifest"),
                game=SimpleNamespace(url="https://example.com/live.game.manifest"),
            )

    monkeypatch.setattr(app_context_module, "LeagueManifestResolver", FakeLeagueManifestResolver)

    create_app_context(
        env_path=env_dir,
        cli_overrides={
            "SOURCE_MODE": "remote_snapshot",
            "REMOTE_LIVE_REGION": "kr",
        },
    )

    assert captured["region"] == "KR"


def test_create_app_context_rejects_partial_remote_snapshot_override(tmp_path: Path) -> None:
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    output_path = tmp_path / "output"
    (env_dir / ".lol.env").write_text(
        f'LOL_OUTPUT_PATH="{output_path}"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="必须同时提供"):
        create_app_context(
            env_path=env_dir,
            cli_overrides={
                "SOURCE_MODE": "remote_snapshot",
                "REMOTE_VERSION": "16.5",
            },
        )


def test_operation_options_defaults() -> None:
    options = OperationOptions()

    assert options.max_workers == DEFAULT_MAX_WORKERS
    assert options.process_events is True
    assert options.integrate_data is False
