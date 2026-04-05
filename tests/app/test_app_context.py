from pathlib import Path
from types import SimpleNamespace

import pytest

import lol_audio_unpack as app_pkg
import lol_audio_unpack.app.context as app_context_impl
from lol_audio_unpack import setup_app
from lol_audio_unpack.app import AppContext, AppContextValidationError, SourceMode, create_app_context
from lol_audio_unpack.config import (
    CONFIG_SECTION,
    load_command_config,
    load_settings,
    resolve_default_path,
    write_settings,
)
from lol_audio_unpack.utils.runtime_paths import detect_runtime_paths

pytestmark = pytest.mark.unit


def _base_settings(tmp_path: Path) -> dict[str, object]:
    return {
        "GAME_PATH": str(tmp_path / "game"),
        "OUTPUT_PATH": str(tmp_path / "output"),
        "GAME_REGION": "zh_CN",
        "EXCLUDE_TYPE": "SFX,MUSIC",
    }


def test_create_app_context_builds_typed_context_from_settings(tmp_path: Path) -> None:
    settings = _base_settings(tmp_path)
    settings["WITH_BP_VO"] = True

    app_context = create_app_context(settings=settings)

    assert isinstance(app_context, AppContext)
    assert app_context.config.game_path == tmp_path / "game"
    assert app_context.config.output_path == tmp_path / "output"
    assert app_context.config.with_bp_vo is True
    assert app_context.paths.audio_path == tmp_path / "output" / "audios"
    assert app_context.paths.manifest_path == tmp_path / "output" / "manifest"
    assert app_context.runtime_cache == {}


def test_create_app_context_applies_explicit_settings(tmp_path: Path) -> None:
    settings = _base_settings(tmp_path)
    settings.update({"EXCLUDE_TYPE": "VO", "GROUP_BY_TYPE": True})

    app_context = create_app_context(settings=settings)

    assert app_context.config.group_by_type is True
    assert app_context.config.exclude_types == ("VO",)
    assert set(app_context.config.include_types) == {"SFX", "MUSIC"}


def test_create_app_context_blank_exclude_type_clears_default(tmp_path: Path) -> None:
    settings = _base_settings(tmp_path)
    settings["EXCLUDE_TYPE"] = ""

    app_context = create_app_context(settings=settings)

    assert app_context.config.exclude_types == ()
    assert set(app_context.config.include_types) == {"VO", "SFX", "MUSIC"}


def test_create_app_context_uses_runtime_default_output_when_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime-root"
    runtime_root.mkdir(parents=True, exist_ok=True)
    game_path = tmp_path / "game"
    monkeypatch.setattr(
        app_context_impl,
        "detect_runtime_paths",
        lambda: detect_runtime_paths(
            is_frozen=False,
            cwd=runtime_root,
            executable=tmp_path / "python" / "python.exe",
        ),
    )

    app_context = create_app_context(
        settings={
            "GAME_PATH": str(game_path),
            "GAME_REGION": "zh_CN",
        }
    )

    assert app_context.config.game_path == game_path
    assert app_context.config.output_path == runtime_root / "output"


def test_create_app_context_ignores_blank_output_setting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime-root"
    runtime_root.mkdir(parents=True, exist_ok=True)
    game_path = tmp_path / "game"
    monkeypatch.setattr(
        app_context_impl,
        "detect_runtime_paths",
        lambda: detect_runtime_paths(
            is_frozen=False,
            cwd=runtime_root,
            executable=tmp_path / "python" / "python.exe",
        ),
    )

    app_context = create_app_context(
        settings={
            "GAME_PATH": str(game_path),
            "GAME_REGION": "zh_CN",
            "OUTPUT_PATH": "   ",
        }
    )

    assert app_context.config.output_path == runtime_root / "output"


def test_create_app_context_resolves_relative_paths_from_runtime_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime-root"
    runtime_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        app_context_impl,
        "detect_runtime_paths",
        lambda: detect_runtime_paths(
            is_frozen=False,
            cwd=runtime_root,
            executable=tmp_path / "python" / "python.exe",
        ),
    )

    app_context = create_app_context(
        settings={
            "GAME_PATH": "./game-client",
            "OUTPUT_PATH": "./custom-output",
            "WWISER_PATH": "./tools/wwiser/wwiser.pyz",
            "GAME_REGION": "zh_CN",
        }
    )

    assert app_context.config.game_path == runtime_root / "game-client"
    assert app_context.config.output_path == runtime_root / "custom-output"
    assert app_context.config.wwiser_path == runtime_root / "tools" / "wwiser" / "wwiser.pyz"


def test_create_app_context_builds_remote_snapshot_config(tmp_path: Path) -> None:
    settings = _base_settings(tmp_path)
    settings.update(
        {
            "SOURCE_MODE": SourceMode.REMOTE_SNAPSHOT.value,
            "REMOTE_VERSION": "15.6",
            "REMOTE_LCU_MANIFEST_URL": "https://example.com/lcu.manifest",
            "REMOTE_GAME_MANIFEST_URL": "https://example.com/game.manifest",
        }
    )

    app_context = create_app_context(settings=settings)

    assert app_context.config.source_mode is SourceMode.REMOTE_SNAPSHOT
    assert app_context.config.remote_snapshot is not None
    assert app_context.config.remote_snapshot.version == "15.6"


def test_create_app_context_missing_required_setting_raises(tmp_path: Path) -> None:
    with pytest.raises(AppContextValidationError, match="GAME_PATH"):
        create_app_context(settings={"OUTPUT_PATH": str(tmp_path / "output")})


def test_setup_app_returns_context_with_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    fake_context = SimpleNamespace(paths=SimpleNamespace(log_path=tmp_path / "output" / "logs"), config=None)

    def fake_create_app_context(*, settings=None, force_reload=False, dev_mode=False, runtime_cache=None):
        captured["settings"] = settings
        captured["force_reload"] = force_reload
        captured["dev_mode"] = dev_mode
        captured["runtime_cache"] = runtime_cache
        return fake_context

    monkeypatch.setattr(app_pkg, "_create_app_context", fake_create_app_context)
    monkeypatch.setattr(app_pkg, "setup_logging", lambda **_kwargs: None)

    result = setup_app(
        dev_mode=True,
        log_level="DEBUG",
        settings={
            "GAME_PATH": str(tmp_path / "game"),
            "OUTPUT_PATH": str(tmp_path / "output"),
        },
    )

    assert result is fake_context
    assert captured["dev_mode"] is True
    assert captured["settings"] == {
        "GAME_PATH": str(tmp_path / "game"),
        "OUTPUT_PATH": str(tmp_path / "output"),
    }


def test_load_settings_reads_lowercase_ini_keys(tmp_path: Path) -> None:
    config_file = tmp_path / "lol-audio-unpack.ini"
    write_settings(
        config_file,
        {
            "GAME_PATH": str(tmp_path / "game"),
            "OUTPUT_PATH": str(tmp_path / "output"),
            "GROUP_BY_TYPE": True,
        },
    )

    settings = load_settings(config_file)

    assert settings == {
        "GAME_PATH": str(tmp_path / "game"),
        "OUTPUT_PATH": str(tmp_path / "output"),
        "GROUP_BY_TYPE": "true",
    }


def test_load_settings_requires_existing_file(tmp_path: Path) -> None:
    config_file = tmp_path / "missing.ini"

    with pytest.raises(FileNotFoundError, match="配置文件不存在"):
        load_settings(config_file)


def test_load_command_config_reads_targets_and_wav_sections(tmp_path: Path) -> None:
    config_file = tmp_path / "lol-audio-unpack.ini"
    config_file.write_text(
        (
            "[app]\n"
            "game_path = ./game\n"
            "\n"
            "[targets]\n"
            "champions = Annie,Ahri\n"
            "\n"
            "[wav]\n"
            "enable = true\n"
        ),
        encoding="utf-8",
    )

    target_config = load_command_config(config_file, command="targets")
    wav_config = load_command_config(config_file, command="wav")

    assert target_config == {
        "champions": "Annie,Ahri",
    }
    assert wav_config == {
        "wav": True,
    }


def test_load_command_config_reads_runtime_and_wav_sections(tmp_path: Path) -> None:
    config_file = tmp_path / "lol-audio-unpack.ini"
    config_file.write_text(
        (
            "[app]\n"
            "game_path = ./game\n"
            "\n"
            "[runtime]\n"
            "max_workers = 8\n"
            "\n"
            "[wav]\n"
            "enable = true\n"
            "wav_workers = 3\n"
            "wav_timeout = 9\n"
            "wav_retries = 4\n"
            "wav_format = float\n"
        ),
        encoding="utf-8",
    )

    runtime_config = load_command_config(config_file, command="runtime")
    wav_config = load_command_config(config_file, command="wav")

    assert runtime_config == {
        "max_workers": 8,
    }
    assert wav_config == {
        "wav": True,
        "wav_workers": 3,
        "wav_timeout": 9,
        "wav_retries": 4,
        "wav_format": "float",
    }


def test_resolve_default_path_uses_runtime_config_root() -> None:
    config_file = resolve_default_path()
    assert config_file.name == "lol-audio-unpack.ini"
    assert config_file.parent.name == "isolated_env"


def test_write_settings_creates_expected_section(tmp_path: Path) -> None:
    config_file = tmp_path / "lol-audio-unpack.ini"

    write_settings(
        config_file,
        {
            "GAME_PATH": str(tmp_path / "game"),
            "OUTPUT_PATH": str(tmp_path / "output"),
        },
    )

    text = config_file.read_text(encoding="utf-8")
    assert f"[{CONFIG_SECTION}]" in text
    assert "game_path =" in text
    assert "output_path =" in text


def test_config_short_names_are_stable_public_api() -> None:
    assert callable(load_settings)
    assert callable(write_settings)
    assert callable(load_command_config)
    assert callable(resolve_default_path)
