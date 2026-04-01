from pathlib import Path
from types import SimpleNamespace

import pytest
from loguru import logger

import lol_audio_unpack as app_pkg
import lol_audio_unpack.app_context as app_context_module
from lol_audio_unpack import setup_app
from lol_audio_unpack.app_context import (
    AppContext,
    AppContextValidationError,
    OperationOptions,
    SourceMode,
    create_app_context,
    initialize_context_from_env,
)
from lol_audio_unpack.utils.runtime_paths import detect_runtime_paths

pytestmark = pytest.mark.unit

DEFAULT_MAX_WORKERS = 4
DEFAULT_WAV_WORKER_COUNT = 2
DEFAULT_WAV_TIMEOUT_SECONDS = 5
DEFAULT_WAV_MAX_RETRIES = 3
DEFAULT_WAV_FORMAT = "pcm16"


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


def _write_named_env_file(env_dir: Path, filename: str, game_path: Path, output_path: Path) -> None:
    """写入指定名称的环境变量文件。"""
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


def test_app_context_does_not_expose_logger_field(tmp_path: Path) -> None:
    """AppContext 只承载共享配置、派生路径与运行时缓存，不暴露 logger 字段。"""
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)

    game_path = tmp_path / "game"
    output_path = tmp_path / "output"
    _write_env_file(env_dir, game_path, output_path)

    app_context = create_app_context(env_path=env_dir)

    assert isinstance(app_context, AppContext)
    assert app_context.runtime_cache == {}
    assert not hasattr(app_context, "logger")


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


def test_create_app_context_blank_exclude_type_override_clears_env_value(tmp_path: Path) -> None:
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)

    game_path = tmp_path / "game"
    output_path = tmp_path / "output"
    _write_env_file(env_dir, game_path, output_path)

    app_context = create_app_context(
        env_path=env_dir,
        cli_overrides={"EXCLUDE_TYPE": ""},
    )

    assert isinstance(app_context, AppContext)
    assert app_context.config.exclude_types == ()
    assert set(app_context.config.include_types) == {"VO", "SFX", "MUSIC"}


def test_create_app_context_default_mode_uses_dot_env_only(tmp_path: Path) -> None:
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)

    game_prod = tmp_path / "game_prod"
    output_prod = tmp_path / "output_prod"
    game_dev = tmp_path / "game_dev"
    output_dev = tmp_path / "output_dev"

    _write_named_env_file(env_dir, ".lol.env", game_prod, output_prod)
    _write_named_env_file(env_dir, ".lol.env.dev", game_dev, output_dev)

    app_context = create_app_context(env_path=env_dir, dev_mode=False)

    assert app_context.config.game_path == game_prod
    assert app_context.config.output_path == output_prod
    assert app_context.config.dev_mode is False


def test_create_app_context_dev_mode_prefers_dot_env_dev(tmp_path: Path) -> None:
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)

    game_prod = tmp_path / "game_prod"
    output_prod = tmp_path / "output_prod"
    game_dev = tmp_path / "game_dev"
    output_dev = tmp_path / "output_dev"

    _write_named_env_file(env_dir, ".lol.env", game_prod, output_prod)
    _write_named_env_file(env_dir, ".lol.env.dev", game_dev, output_dev)

    app_context = create_app_context(env_path=env_dir, dev_mode=True)

    assert app_context.config.game_path == game_dev
    assert app_context.config.output_path == output_dev
    assert app_context.config.dev_mode is True


def test_create_app_context_dev_mode_falls_back_to_dot_env_when_dev_missing(tmp_path: Path) -> None:
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)

    game_prod = tmp_path / "game_prod"
    output_prod = tmp_path / "output_prod"

    _write_named_env_file(env_dir, ".lol.env", game_prod, output_prod)

    app_context = create_app_context(env_path=env_dir, dev_mode=True)

    assert app_context.config.game_path == game_prod
    assert app_context.config.output_path == output_prod
    assert app_context.config.dev_mode is True


def test_create_app_context_non_dev_mode_does_not_read_dot_env_dev_alone(tmp_path: Path) -> None:
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)

    game_dev = tmp_path / "game_dev"
    output_dev = tmp_path / "output_dev"

    _write_named_env_file(env_dir, ".lol.env.dev", game_dev, output_dev)

    with pytest.raises(AppContextValidationError, match="GAME_PATH"):
        create_app_context(env_path=env_dir, dev_mode=False)


def test_create_app_context_missing_env_file_logs_debug_not_warning(tmp_path: Path) -> None:
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    game_path = tmp_path / "game"
    output_path = tmp_path / "output"

    log_lines: list[str] = []
    logger.enable("lol_audio_unpack")
    sink_id = logger.add(
        lambda message: log_lines.append(str(message).rstrip()),
        format="{level}|{message}",
        level="DEBUG",
    )
    try:
        create_app_context(
            env_path=env_dir,
            dev_mode=False,
            cli_overrides={
                "GAME_PATH": str(game_path),
                "OUTPUT_PATH": str(output_path),
            },
        )
    finally:
        logger.remove(sink_id)
        logger.disable("lol_audio_unpack")

    assert any(line.startswith("DEBUG|环境变量文件不存在:") for line in log_lines)
    assert not any(line.startswith("WARNING|环境变量文件不存在:") for line in log_lines)


def test_create_app_context_system_env_overrides_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)

    game_dotenv = tmp_path / "game_dotenv"
    output_dotenv = tmp_path / "output_dotenv"
    game_env = tmp_path / "game_env"
    output_env = tmp_path / "output_env"

    _write_named_env_file(env_dir, ".lol.env", game_dotenv, output_dotenv)
    monkeypatch.setenv("LOL_GAME_PATH", str(game_env))
    monkeypatch.setenv("LOL_OUTPUT_PATH", str(output_env))

    app_context = create_app_context(env_path=env_dir, dev_mode=False)

    assert app_context.config.game_path == game_env
    assert app_context.config.output_path == output_env


def test_create_app_context_ignores_unknown_lol_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)

    game_path = tmp_path / "game"
    output_path = tmp_path / "output"

    _write_named_env_file(env_dir, ".lol.env", game_path, output_path)
    monkeypatch.setenv("LOL_UNKNOWN_KEY", "unexpected")

    app_context = create_app_context(env_path=env_dir, dev_mode=False)

    assert app_context.config.game_path == game_path
    assert app_context.config.output_path == output_path


def test_create_app_context_missing_required_raises_fast(tmp_path: Path) -> None:
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)

    with pytest.raises(AppContextValidationError, match="GAME_PATH"):
        create_app_context(env_path=env_dir, dev_mode=False)


def test_create_app_context_uses_runtime_defaults_when_env_path_and_output_path_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime-root"
    runtime_root.mkdir(parents=True, exist_ok=True)
    game_path = tmp_path / "game"
    (runtime_root / ".lol.env").write_text(
        "\n".join(
            [
                f'LOL_GAME_PATH="{game_path}"',
                'LOL_GAME_REGION="zh_CN"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("LOL_GAME_PATH", raising=False)
    monkeypatch.delenv("LOL_OUTPUT_PATH", raising=False)
    monkeypatch.setattr(
        app_context_module,
        "detect_runtime_paths",
        lambda: detect_runtime_paths(
            is_frozen=False,
            cwd=runtime_root,
            executable=tmp_path / "python" / "python.exe",
        ),
    )

    app_context = create_app_context()

    assert app_context.config.game_path == game_path
    assert app_context.config.output_path == runtime_root / "output"
    assert app_context.paths.log_path == runtime_root / "output" / "logs"


def test_create_app_context_ignores_blank_output_override_from_gui(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime-root"
    runtime_root.mkdir(parents=True, exist_ok=True)
    game_path = tmp_path / "game"
    monkeypatch.delenv("LOL_GAME_PATH", raising=False)
    monkeypatch.delenv("LOL_OUTPUT_PATH", raising=False)
    monkeypatch.setattr(
        app_context_module,
        "detect_runtime_paths",
        lambda: detect_runtime_paths(
            is_frozen=False,
            cwd=runtime_root,
            executable=tmp_path / "python" / "python.exe",
        ),
    )

    app_context = create_app_context(
        cli_overrides={
            "SOURCE_MODE": "local_path",
            "GAME_PATH": str(game_path),
            "OUTPUT_PATH": "",
        }
    )

    assert app_context.config.game_path == game_path
    assert app_context.config.output_path == runtime_root / "output"


def test_create_app_context_ignores_blank_output_from_env_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime-root"
    runtime_root.mkdir(parents=True, exist_ok=True)
    game_path = tmp_path / "game"
    (runtime_root / ".lol.env").write_text(
        "\n".join(
            [
                f'LOL_GAME_PATH="{game_path}"',
                "LOL_OUTPUT_PATH=''",
                'LOL_GAME_REGION="zh_CN"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("LOL_GAME_PATH", raising=False)
    monkeypatch.delenv("LOL_OUTPUT_PATH", raising=False)
    monkeypatch.setattr(
        app_context_module,
        "detect_runtime_paths",
        lambda: detect_runtime_paths(
            is_frozen=False,
            cwd=runtime_root,
            executable=tmp_path / "python" / "python.exe",
        ),
    )

    app_context = create_app_context()

    assert app_context.config.game_path == game_path
    assert app_context.config.output_path == runtime_root / "output"


def test_create_app_context_resolves_relative_cli_paths_from_runtime_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime-root"
    runtime_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.delenv("LOL_GAME_PATH", raising=False)
    monkeypatch.delenv("LOL_OUTPUT_PATH", raising=False)
    monkeypatch.delenv("LOL_WWISER_PATH", raising=False)
    monkeypatch.setattr(
        app_context_module,
        "detect_runtime_paths",
        lambda: detect_runtime_paths(
            is_frozen=True,
            cwd=tmp_path / "shortcut-workdir",
            executable=runtime_root / "LolAudioUnpack.exe",
        ),
    )

    app_context = create_app_context(
        cli_overrides={
            "SOURCE_MODE": "local_path",
            "GAME_PATH": "./game-client",
            "OUTPUT_PATH": "./custom-output",
            "WWISER_PATH": "./tools/wwiser/wwiser.pyz",
        }
    )

    assert app_context.config.game_path == runtime_root / "game-client"
    assert app_context.config.output_path == runtime_root / "custom-output"
    assert app_context.config.wwiser_path == runtime_root / "tools" / "wwiser" / "wwiser.pyz"
    assert app_context.paths.log_path == runtime_root / "custom-output" / "logs"


def test_create_app_context_resolves_relative_env_paths_from_runtime_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime-root"
    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / ".lol.env").write_text(
        "\n".join(
            [
                'LOL_GAME_PATH="./game-client"',
                'LOL_OUTPUT_PATH="./custom-output"',
                'LOL_WWISER_PATH="./tools/wwiser/wwiser.pyz"',
                'LOL_GAME_REGION="zh_CN"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("LOL_GAME_PATH", raising=False)
    monkeypatch.delenv("LOL_OUTPUT_PATH", raising=False)
    monkeypatch.delenv("LOL_WWISER_PATH", raising=False)
    monkeypatch.setattr(
        app_context_module,
        "detect_runtime_paths",
        lambda: detect_runtime_paths(
            is_frozen=True,
            cwd=tmp_path / "shortcut-workdir",
            executable=runtime_root / "LolAudioUnpack.exe",
        ),
    )

    app_context = create_app_context()

    assert app_context.config.game_path == runtime_root / "game-client"
    assert app_context.config.output_path == runtime_root / "custom-output"
    assert app_context.config.wwiser_path == runtime_root / "tools" / "wwiser" / "wwiser.pyz"
    assert app_context.paths.log_path == runtime_root / "custom-output" / "logs"


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


def test_create_app_context_derives_wav_path(tmp_path: Path) -> None:
    env_dir = tmp_path / "env"
    game_path = tmp_path / "game"
    output_path = tmp_path / "output"
    env_dir.mkdir()
    game_path.mkdir()
    _write_env_file(env_dir, game_path, output_path)

    app_context = create_app_context(env_path=env_dir)

    assert app_context.paths.audio_path == output_path / "audios"
    assert app_context.paths.wav_path == output_path / "wavs"
    assert not app_context.paths.wav_path.exists()


def test_operation_options_defaults() -> None:
    options = OperationOptions()

    assert options.max_workers == DEFAULT_MAX_WORKERS
    assert options.process_events is True
    assert options.integrate_data is False
    assert options.wav_output.enabled is False
    assert options.wav_output.worker_count == DEFAULT_WAV_WORKER_COUNT
    assert options.wav_output.timeout_seconds == DEFAULT_WAV_TIMEOUT_SECONDS
    assert options.wav_output.max_retries == DEFAULT_WAV_MAX_RETRIES
    assert options.wav_output.format == DEFAULT_WAV_FORMAT
