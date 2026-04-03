from pathlib import Path
from types import SimpleNamespace

import pytest

import lol_audio_unpack.cli.dispatch as dispatch_cli
import lol_audio_unpack.cli.runtime as runtime_cli
from lol_audio_unpack.app_context import SourceMode
from lol_audio_unpack.cli.cli import _detect_mode
from lol_audio_unpack.cli.parser import create_parser

pytestmark = pytest.mark.unit

EXPECTED_WAV_WORKERS = 4
EXPECTED_WAV_TIMEOUT = 7
EXPECTED_WAV_RETRIES = 5
EXPECTED_CONFIG_MAX_WORKERS = 6


def test_detect_mode_from_unpack_script_name() -> None:
    assert _detect_mode("unpack") == "unpack"
    assert _detect_mode("unpack.exe") == "unpack"


def test_detect_mode_from_mapping_script_name() -> None:
    assert _detect_mode("mapping") == "mapping"
    assert _detect_mode("mapping.exe") == "mapping"


def test_parse_ids() -> None:
    assert runtime_cli.parse_ids(None) is None
    assert runtime_cli.parse_ids("all") is None
    assert runtime_cli.parse_ids("1,2, 3 , ,") == ["1", "2", "3"]


def test_validate_args_requires_action_subcommand() -> None:
    parser = create_parser()
    args = parser.parse_args([])

    with pytest.raises(SystemExit) as exc:
        runtime_cli.validate_args(args, parser)

    assert exc.value.code == 1


def test_validate_args_deduplicates_action_order() -> None:
    parser = create_parser()
    args = parser.parse_args(["extract", "update", "extract"])

    runtime_cli.validate_args(args, parser)

    assert args.actions == ["extract", "update"]


def test_validate_config_mode_rejects_any_extra_manual_args() -> None:
    with pytest.raises(SystemExit) as exc:
        runtime_cli._validate_config_argv(["update", "-c", "--game-path", "game-root"])

    assert exc.value.code == 1


def test_validate_config_mode_rejects_manual_args_before_config_flag() -> None:
    with pytest.raises(SystemExit) as exc:
        runtime_cli._validate_config_argv(["update", "--force", "-c", "config.ini"])

    assert exc.value.code == 1


def test_validate_config_mode_rejects_dev_flag_in_config_mode() -> None:
    with pytest.raises(SystemExit) as exc:
        runtime_cli._validate_config_argv(["update", "--dev", "-c"])

    assert exc.value.code == 1


def test_validate_config_mode_allows_only_actions_and_config_path() -> None:
    runtime_cli._validate_config_argv(["update", "extract", "--config-file", "config.ini"])


def test_validate_args_wav_tuning_requires_wav_flag() -> None:
    parser = create_parser()
    args = parser.parse_args(["extract", "--wav-workers", "4"])

    with pytest.raises(SystemExit) as exc:
        runtime_cli.validate_args(args, parser)

    assert exc.value.code == 1


def test_validate_args_mapping_allows_integrate_data() -> None:
    parser = create_parser()
    args = parser.parse_args(["mapping", "--integrate-data"])

    runtime_cli.validate_args(args, parser)


def test_mapping_defaults_integrate_data_to_true() -> None:
    parser = create_parser()
    args = parser.parse_args(["mapping"])

    opts = runtime_cli.build_operation_options(args)

    assert opts.integrate_data is True


def test_build_context_settings_only_keeps_explicit_values() -> None:
    parser = create_parser()
    args = parser.parse_args(
        [
            "update",
            "--game-path",
            "game-root",
            "--output-path",
            "output-root",
            "--game-region",
            "en_US",
            "--exclude-type",
            "VO",
            "--wwiser-path",
            "tools/wwiser.pyz",
            "--group-by-type",
        ]
    )

    settings = runtime_cli.build_context_settings(args)

    assert settings == {
        "GAME_PATH": "game-root",
        "OUTPUT_PATH": "output-root",
        "GAME_REGION": "en_US",
        "EXCLUDE_TYPE": "VO",
        "WWISER_PATH": "tools/wwiser.pyz",
        "GROUP_BY_TYPE": True,
    }


def test_build_context_settings_includes_remote_options_and_bp_voice() -> None:
    parser = create_parser()
    args = parser.parse_args(
        [
            "update",
            "--source-mode",
            "remote_snapshot",
            "--remote-live-region",
            "NA",
            "--cleanup-remote",
            "--with-bp-vo",
        ]
    )

    settings = runtime_cli.build_context_settings(args)

    assert settings == {
        "SOURCE_MODE": "remote_snapshot",
        "REMOTE_LIVE_REGION": "NA",
        "CLEANUP_REMOTE": True,
        "WITH_BP_VO": True,
    }


def test_initialize_app_passes_settings_to_setup_app(monkeypatch, tmp_path: Path) -> None:
    parser = create_parser()
    game_path = tmp_path / "game"
    game_path.mkdir(parents=True, exist_ok=True)

    args = parser.parse_args(
        [
            "update",
            "--game-path",
            str(game_path),
            "--output-path",
            str(tmp_path / "output"),
            "--game-region",
            "en_US",
            "--exclude-type",
            "VO",
            "--wwiser-path",
            str(tmp_path / "wwiser.pyz"),
            "--group-by-type",
        ]
    )

    captured = {}
    fake_context = SimpleNamespace(config=SimpleNamespace(game_path=game_path, source_mode=SourceMode.LOCAL_PATH))

    def fake_setup_app(*, dev_mode=False, log_level="INFO", **kwargs):
        captured["dev_mode"] = dev_mode
        captured["log_level"] = log_level
        captured["kwargs"] = kwargs
        return fake_context

    monkeypatch.setattr(runtime_cli, "setup_app", fake_setup_app)

    ctx = runtime_cli.initialize_app(args)

    assert ctx == fake_context
    assert captured["kwargs"]["settings"] == {
        "GAME_PATH": str(game_path),
        "OUTPUT_PATH": str(tmp_path / "output"),
        "GAME_REGION": "en_US",
        "EXCLUDE_TYPE": "VO",
        "WWISER_PATH": str(tmp_path / "wwiser.pyz"),
        "GROUP_BY_TYPE": True,
    }


def test_apply_config_profile_loads_command_section(monkeypatch, tmp_path: Path) -> None:
    parser = create_parser()
    config_file = tmp_path / "lol-audio-unpack.ini"
    args = parser.parse_args(["update", "extract", "-c", str(config_file)])

    monkeypatch.setattr(
        runtime_cli,
        "load_settings_from_config_file",
        lambda path, require_exists=True: {"GAME_PATH": str(tmp_path / "game")},
    )
    monkeypatch.setattr(
        runtime_cli,
        "load_command_config_from_file",
        lambda path, command, require_exists=True: {
            "targets": {"champions": "Annie,Ahri"},
            "update": {"skip_events": True},
            "extract": {"wav": True},
        }.get(command, {}),
    )

    runtime_cli._apply_config_profile(args)

    assert args.champions == "Annie,Ahri"
    assert args.skip_events is True
    assert args.wav is True
    assert args._loaded_settings == {"GAME_PATH": str(tmp_path / "game")}


def test_apply_config_profile_loads_runtime_and_wav_sections(monkeypatch, tmp_path: Path) -> None:
    parser = create_parser()
    config_file = tmp_path / "lol-audio-unpack.ini"
    args = parser.parse_args(["extract", "-c", str(config_file)])

    monkeypatch.setattr(
        runtime_cli,
        "load_settings_from_config_file",
        lambda path, require_exists=True: {"GAME_PATH": str(tmp_path / "game")},
    )
    monkeypatch.setattr(
        runtime_cli,
        "load_command_config_from_file",
        lambda path, command, require_exists=True: {
            "runtime": {"max_workers": EXPECTED_CONFIG_MAX_WORKERS},
            "extract": {"wav": True},
            "wav": {
                "wav_workers": EXPECTED_WAV_WORKERS,
                "wav_timeout": EXPECTED_WAV_TIMEOUT,
                "wav_retries": EXPECTED_WAV_RETRIES,
                "wav_format": "auto",
            },
        }.get(command, {}),
    )

    runtime_cli._apply_config_profile(args)

    assert args.max_workers == EXPECTED_CONFIG_MAX_WORKERS
    assert args.wav is True
    assert args.wav_workers == EXPECTED_WAV_WORKERS
    assert args.wav_timeout == EXPECTED_WAV_TIMEOUT
    assert args.wav_retries == EXPECTED_WAV_RETRIES
    assert args.wav_format == "auto"


def test_initialize_app_in_config_mode_uses_loaded_settings(monkeypatch, tmp_path: Path) -> None:
    parser = create_parser()
    config_file = tmp_path / "lol-audio-unpack.ini"
    game_path = tmp_path / "game"
    game_path.mkdir(parents=True, exist_ok=True)
    args = parser.parse_args(["update", "-c", str(config_file)])
    args._loaded_settings = {
        "GAME_PATH": str(game_path),
        "OUTPUT_PATH": str(tmp_path / "output"),
        "SOURCE_MODE": "local_path",
    }

    captured = {}
    fake_context = SimpleNamespace(config=SimpleNamespace(game_path=game_path, source_mode=SourceMode.LOCAL_PATH))

    def fake_setup_app(*, dev_mode=False, log_level="INFO", **kwargs):
        captured["settings"] = kwargs["settings"]
        return fake_context

    monkeypatch.setattr(runtime_cli, "setup_app", fake_setup_app)

    runtime_cli.initialize_app(args)

    assert captured["settings"] == {
        "GAME_PATH": str(game_path),
        "OUTPUT_PATH": str(tmp_path / "output"),
        "SOURCE_MODE": "local_path",
    }


def test_build_operation_options_includes_wav_settings() -> None:
    parser = create_parser()
    args = parser.parse_args(
        [
            "extract",
            "--wav",
            "--wav-workers",
            str(EXPECTED_WAV_WORKERS),
            "--wav-timeout",
            str(EXPECTED_WAV_TIMEOUT),
            "--wav-retries",
            str(EXPECTED_WAV_RETRIES),
            "--wav-format",
            "auto",
        ]
    )

    opts = runtime_cli.build_operation_options(args)

    assert opts.wav_output.enabled is True
    assert opts.wav_output.worker_count == EXPECTED_WAV_WORKERS
    assert opts.wav_output.timeout_seconds == EXPECTED_WAV_TIMEOUT
    assert opts.wav_output.max_retries == EXPECTED_WAV_RETRIES
    assert opts.wav_output.format == "auto"


def test_execute_update_operations_all() -> None:
    parser = create_parser()
    args = parser.parse_args(["update"])

    calls = {}

    class FakeApp:
        def update(self, opts, *, target="all"):
            calls["target"] = target
            calls["opts"] = opts

    dispatch_cli.run_update(args, FakeApp())

    assert calls["target"] == "all"
    assert calls["opts"].force_update is False
    assert calls["opts"].process_events is True


def test_execute_update_operations_shared_targets_cover_both_entity_types(monkeypatch) -> None:
    parser = create_parser()
    args = parser.parse_args(["update", "--champions", "Annie,Ahri", "--maps", "11,12"])
    monkeypatch.setattr(dispatch_cli, "resolve_cli_champion_ids", lambda *_args, **_kwargs: (1, 2))

    class FakeApp:
        def update(self, opts, *, target="all"):
            assert target == "all"
            assert opts.champion_ids == (1, 2)
            assert opts.map_ids == (11, 12)

    dispatch_cli.run_update(
        args,
        FakeApp(),
    )


def test_execute_extract_operations_uses_standard_stage_logs(monkeypatch) -> None:
    parser = create_parser()
    args = parser.parse_args(["extract"])
    stage_calls = []

    monkeypatch.setattr(
        dispatch_cli, "_log_stage_start", lambda stage, detail=None: stage_calls.append(("start", stage, detail))
    )
    monkeypatch.setattr(
        dispatch_cli, "_log_stage_done", lambda stage, detail=None: stage_calls.append(("done", stage, detail))
    )

    class FakeApp:
        def extract(self, _opts, **_kwargs) -> None:
            return None

    dispatch_cli.run_extract(args, FakeApp())

    assert stage_calls == [
        ("start", "音频解包", "所有音频（英雄和地图）"),
        ("done", "音频解包", "所有音频（英雄和地图）"),
    ]


def test_execute_extract_operations_forwards_detached_wav_flags(monkeypatch) -> None:
    parser = create_parser()
    args = parser.parse_args(["extract", "--wav"])
    captured_kwargs = {}

    monkeypatch.setattr(dispatch_cli, "_log_stage_start", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dispatch_cli, "_log_stage_done", lambda *_args, **_kwargs: None)

    class FakeApp:
        def extract(self, _opts, **kwargs):
            captured_kwargs.update(kwargs)
            return SimpleNamespace(poll=lambda: None, read_progress_snapshot=lambda: None, job_label="cli-test")

    handle = dispatch_cli.run_extract(args, FakeApp())

    assert handle is not None
    assert captured_kwargs["detach_wav_sidecar"] is True
    assert str(captured_kwargs["wav_job_label"]).startswith("cli-")


def test_execute_mapping_operations_defaults_to_native_hirc_without_wwiser(monkeypatch) -> None:
    parser = create_parser()
    args = parser.parse_args(["mapping"])

    class FakeApp:
        def mapping(self, opts, **kwargs):
            assert opts.wwiser_path is None if hasattr(opts, "wwiser_path") else True
            assert kwargs == {"include_champions": True, "include_maps": True}

    monkeypatch.setattr(dispatch_cli, "_log_stage_start", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dispatch_cli, "_log_stage_done", lambda *_args, **_kwargs: None)

    dispatch_cli.run_mapping(args, FakeApp())
