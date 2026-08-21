from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

import lol_audio_unpack.cli.cli as cli_module
import lol_audio_unpack.cli.dispatch as dispatch_cli
import lol_audio_unpack.cli.runtime as runtime_cli
from lol_audio_unpack.app.results import EntityResult, ResultStatus, StageResult
from lol_audio_unpack.app.types import SourceMode
from lol_audio_unpack.cli.cli import _detect_mode
from lol_audio_unpack.cli.parser import create_parser

pytestmark = pytest.mark.unit

EXPECTED_WAV_WORKERS = 4
EXPECTED_WAV_TIMEOUT = 7
EXPECTED_WAV_RETRIES = 5
EXPECTED_CONFIG_MAX_WORKERS = 6
EXIT_SUCCESS = 0
EXIT_FAILED = 1
EXIT_INPUT = 2
EXIT_PARTIAL = 3
EXIT_CANCELLED = 130


def _stage(stage: str, status: ResultStatus = ResultStatus.SUCCESS) -> StageResult:
    return StageResult.from_entities(stage, (EntityResult("champion", 1, status),))


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

    with pytest.raises(runtime_cli.CliInputError):
        runtime_cli.validate_args(args, parser)


def test_validate_args_deduplicates_action_order() -> None:
    parser = create_parser()
    args = parser.parse_args(["extract", "wav", "update", "extract"])

    runtime_cli.validate_args(args, parser)

    assert args.actions == ["extract", "wav", "update"]


def test_validate_config_mode_rejects_any_extra_manual_args() -> None:
    with pytest.raises(runtime_cli.CliInputError):
        runtime_cli._validate_config_argv(["-c", "--game-path", "game-root"])


def test_validate_config_mode_rejects_actions_in_config_mode() -> None:
    with pytest.raises(runtime_cli.CliInputError):
        runtime_cli._validate_config_argv(["update", "-c", "config.ini"])


def test_validate_config_mode_rejects_dev_flag_in_config_mode() -> None:
    with pytest.raises(runtime_cli.CliInputError):
        runtime_cli._validate_config_argv(["update", "--dev", "-c"])


def test_validate_config_mode_allows_only_config_path() -> None:
    runtime_cli._validate_config_argv(["--config-file", "config.ini"])


def test_validate_args_rejects_wav_tuning_without_wav_action() -> None:
    parser = create_parser()
    args = parser.parse_args(["extract", "--wav-workers", "4"])

    with pytest.raises(runtime_cli.CliInputError):
        runtime_cli.validate_args(args, parser)


def test_validate_args_mapping_allows_integrate_data() -> None:
    parser = create_parser()
    args = parser.parse_args(["mapping", "--integrate-data"])

    runtime_cli.validate_args(args, parser)


def test_mapping_defaults_integrate_data_to_true() -> None:
    parser = create_parser()
    args = parser.parse_args(["mapping"])

    opts = runtime_cli.build_options(args)

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

    settings = runtime_cli.build_settings(args)

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

    settings = runtime_cli.build_settings(args)

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
    args = parser.parse_args(["-c", str(config_file)])

    monkeypatch.setattr(
        runtime_cli,
        "load_settings",
        lambda path, require_exists=True: {"GAME_PATH": str(tmp_path / "game")},
    )
    monkeypatch.setattr(
        runtime_cli,
        "load_command_config",
        lambda path, command, require_exists=True: {
            "targets": {"champions": "Annie,Ahri"},
            "update": {"_update_enabled": True, "skip_events": True},
            "extract": {"_extract_enabled": True},
            "wav": {"wav": True},
        }.get(command, {}),
    )

    runtime_cli._apply_config_profile(args)

    assert args.actions == ["update", "extract", "wav"]
    assert args.champions == "Annie,Ahri"
    assert args.skip_events is True
    assert args.wav is True
    assert args._loaded_settings == {"GAME_PATH": str(tmp_path / "game")}


def test_apply_config_profile_loads_runtime_and_wav_sections(monkeypatch, tmp_path: Path) -> None:
    parser = create_parser()
    config_file = tmp_path / "lol-audio-unpack.ini"
    args = parser.parse_args(["-c", str(config_file)])

    monkeypatch.setattr(
        runtime_cli,
        "load_settings",
        lambda path, require_exists=True: {"GAME_PATH": str(tmp_path / "game")},
    )
    monkeypatch.setattr(
        runtime_cli,
        "load_command_config",
        lambda path, command, require_exists=True: {
            "runtime": {"max_workers": EXPECTED_CONFIG_MAX_WORKERS},
            "extract": {"_extract_enabled": True},
            "wav": {
                "wav": True,
                "wav_workers": EXPECTED_WAV_WORKERS,
                "wav_timeout": EXPECTED_WAV_TIMEOUT,
                "wav_retries": EXPECTED_WAV_RETRIES,
                "wav_format": "auto",
            },
        }.get(command, {}),
    )

    runtime_cli._apply_config_profile(args)

    assert args.actions == ["extract", "wav"]
    assert args.max_workers == EXPECTED_CONFIG_MAX_WORKERS
    assert args.wav is True
    assert args.wav_workers == EXPECTED_WAV_WORKERS
    assert args.wav_timeout == EXPECTED_WAV_TIMEOUT
    assert args.wav_retries == EXPECTED_WAV_RETRIES
    assert args.wav_format == "auto"


def test_config_mode_allows_disabled_wav_section_with_tuning_values(monkeypatch, tmp_path: Path) -> None:
    """配置文件中显式关闭 WAV 时，不应因为保留调参项而阻止 extract 执行。"""
    parser = create_parser()
    config_file = tmp_path / "lol-audio-unpack.ini"
    args = parser.parse_args(["-c", str(config_file)])
    warnings: list[str] = []

    monkeypatch.setattr(
        runtime_cli,
        "load_settings",
        lambda path, require_exists=True: {"GAME_PATH": str(tmp_path / "game")},
    )
    monkeypatch.setattr(
        runtime_cli,
        "load_command_config",
        lambda path, command, require_exists=True: {
            "extract": {"_extract_enabled": True},
            "wav": {
                "wav": False,
                "wav_workers": EXPECTED_WAV_WORKERS,
                "wav_timeout": EXPECTED_WAV_TIMEOUT,
                "wav_retries": EXPECTED_WAV_RETRIES,
                "wav_format": "auto",
            },
        }.get(command, {}),
    )
    monkeypatch.setattr(runtime_cli.logger, "warning", lambda message, *args: warnings.append(message.format(*args)))

    runtime_cli._apply_config_profile(args)
    runtime_cli.validate_args(args, parser)

    assert args.actions == ["extract"]
    assert args.wav is False
    assert args.wav_workers is None
    assert args.wav_timeout is None
    assert args.wav_retries is None
    assert args.wav_format is None
    assert warnings == ["[wav] enable=false，已忽略同组细节参数: wav_workers, wav_timeout, wav_retries, wav_format"]


def test_validate_args_config_mode_requires_enabled_action(monkeypatch, tmp_path: Path) -> None:
    parser = create_parser()
    config_file = tmp_path / "lol-audio-unpack.ini"
    args = parser.parse_args(["-c", str(config_file)])

    monkeypatch.setattr(
        runtime_cli,
        "load_settings",
        lambda path, require_exists=True: {"GAME_PATH": str(tmp_path / "game")},
    )
    monkeypatch.setattr(
        runtime_cli,
        "load_command_config",
        lambda path, command, require_exists=True: {},
    )

    runtime_cli._apply_config_profile(args)

    with pytest.raises(runtime_cli.CliInputError):
        runtime_cli.validate_args(args, parser)


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
            "wav",
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

    opts = runtime_cli.build_options(args)

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
            return _stage("update")

    result = dispatch_cli.run_update(args, FakeApp())

    assert calls["target"] == "all"
    assert calls["opts"].force_update is False
    assert calls["opts"].process_events is True
    assert result.status is ResultStatus.SUCCESS


def test_execute_update_operations_shared_targets_cover_both_entity_types(monkeypatch) -> None:
    parser = create_parser()
    args = parser.parse_args(["update", "--champions", "Annie,Ahri", "--maps", "11,12"])
    monkeypatch.setattr(dispatch_cli, "resolve_champion_ids", lambda *_args, **_kwargs: (1, 2))

    class FakeApp:
        def update(self, opts, *, target="all"):
            assert target == "all"
            assert opts.champion_ids == (1, 2)
            assert opts.map_ids == (11, 12)
            return _stage("update")

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
        def extract(self, _opts, **_kwargs) -> StageResult:
            return _stage("extract")

    dispatch_cli.run_extract(args, FakeApp())

    assert stage_calls == [
        ("start", "音频解包", "所有音频（英雄和地图）"),
        ("done", "音频解包", "所有音频（英雄和地图）"),
    ]


def test_execute_extract_operations_no_longer_forwards_wav_sidecar_flags(monkeypatch) -> None:
    parser = create_parser()
    args = parser.parse_args(["extract", "wav"])
    captured_kwargs = {}

    monkeypatch.setattr(dispatch_cli, "_log_stage_start", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dispatch_cli, "_log_stage_done", lambda *_args, **_kwargs: None)

    class FakeApp:
        def extract(self, opts, **kwargs):
            assert opts.wav_output.enabled is True
            captured_kwargs.update(kwargs)
            return _stage("extract")

    handle = dispatch_cli.run_extract(args, FakeApp())

    assert handle.status is ResultStatus.SUCCESS
    assert "detach_wav" not in captured_kwargs
    assert "wav_job_label" not in captured_kwargs


def test_run_wav_executes_dedicated_stage(monkeypatch) -> None:
    parser = create_parser()
    args = parser.parse_args(["wav", "--wav-workers", "4"])
    captured = {}
    stage_calls = []

    monkeypatch.setattr(
        dispatch_cli, "_log_stage_start", lambda stage, detail=None: stage_calls.append(("start", stage, detail))
    )
    monkeypatch.setattr(
        dispatch_cli, "_log_stage_done", lambda stage, detail=None: stage_calls.append(("done", stage, detail))
    )

    class FakeApp:
        def transcode_wav(self, opts, **kwargs) -> StageResult:
            captured["enabled"] = opts.wav_output.enabled
            captured["workers"] = opts.wav_output.worker_count
            captured["kwargs"] = kwargs
            return StageResult("wav")

    dispatch_cli.run_wav(args, FakeApp())

    assert stage_calls == [
        ("start", "WAV 转码", "消费当前 audios 输出树"),
        ("done", "WAV 转码", "消费当前 audios 输出树"),
    ]
    assert captured == {
        "enabled": True,
        "workers": EXPECTED_WAV_WORKERS,
        "kwargs": {},
    }


def test_run_wav_resolves_targets_before_transcoding(monkeypatch) -> None:
    parser = create_parser()
    args = parser.parse_args(["wav", "--champions", "Annie,Ahri", "--maps", "11"])
    captured = {}

    monkeypatch.setattr(dispatch_cli, "resolve_champion_ids", lambda *_args, **_kwargs: (1, 103))

    class FakeApp:
        def transcode_wav(self, opts, **kwargs) -> StageResult:
            captured["champion_ids"] = opts.champion_ids
            captured["map_ids"] = opts.map_ids
            return StageResult("wav")

    dispatch_cli.run_wav(args, FakeApp())

    assert captured == {
        "champion_ids": (1, 103),
        "map_ids": (11,),
    }


def test_execute_mapping_operations_defaults_to_native_hirc_without_wwiser(monkeypatch) -> None:
    parser = create_parser()
    args = parser.parse_args(["mapping"])

    class FakeApp:
        def mapping(self, opts, **kwargs):
            assert opts.wwiser_path is None if hasattr(opts, "wwiser_path") else True
            assert kwargs == {"include_champions": True, "include_maps": True}
            return _stage("mapping")

    monkeypatch.setattr(dispatch_cli, "_log_stage_start", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dispatch_cli, "_log_stage_done", lambda *_args, **_kwargs: None)

    dispatch_cli.run_mapping(args, FakeApp())


def test_run_extract_partial_does_not_log_stage_done(monkeypatch) -> None:
    parser = create_parser()
    args = parser.parse_args(["extract"])
    stage_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        dispatch_cli, "_log_stage_start", lambda stage, detail=None: stage_calls.append(("start", stage))
    )
    monkeypatch.setattr(dispatch_cli, "_log_stage_done", lambda stage, detail=None: stage_calls.append(("done", stage)))

    class FakeApp:
        def extract(self, _opts, **_kwargs) -> StageResult:
            return _stage("extract", ResultStatus.PARTIAL)

    result = dispatch_cli.run_extract(args, FakeApp())

    assert result.status is ResultStatus.PARTIAL
    assert stage_calls == [("start", "音频解包")]


def test_run_wav_filters_targets_to_successful_extract_entities(monkeypatch) -> None:
    parser = create_parser()
    args = parser.parse_args(["extract", "wav", "--champions", "1,2", "--maps", "11"])
    captured: dict[str, object] = {}
    monkeypatch.setattr(dispatch_cli, "_resolve_targets", lambda *_args, **_kwargs: ((1, 2), (11,)))

    extract_result = StageResult.from_entities(
        "extract",
        (
            EntityResult("champion", 1, ResultStatus.SUCCESS, artifacts=("audios/1/sample.wem",)),
            EntityResult("champion", 2, ResultStatus.FAILED),
            EntityResult("champion", 3, ResultStatus.SUCCESS),
            EntityResult("map", 11, ResultStatus.PARTIAL, artifacts=("audios/11/sample.wem",)),
        ),
    )

    class FakeApp:
        def transcode_wav(self, opts) -> StageResult:
            captured["champion_ids"] = opts.champion_ids
            captured["map_ids"] = opts.map_ids
            return StageResult("wav")

    result = dispatch_cli.run_wav(args, FakeApp(), extract_result=extract_result)

    assert result.status is ResultStatus.SUCCESS
    assert captured == {"champion_ids": (1,), "map_ids": (11,)}


def test_run_wav_does_not_consume_stale_targets_after_extract_no_op(monkeypatch) -> None:
    parser = create_parser()
    args = parser.parse_args(["extract", "wav", "--champions", "1", "--maps", "11"])
    captured: dict[str, object] = {}
    monkeypatch.setattr(dispatch_cli, "_resolve_targets", lambda *_args, **_kwargs: ((1,), (11,)))

    class FakeApp:
        def transcode_wav(self, opts) -> StageResult:
            captured["champion_ids"] = opts.champion_ids
            captured["map_ids"] = opts.map_ids
            return StageResult("wav")

    result = dispatch_cli.run_wav(
        args,
        FakeApp(),
        extract_result=StageResult.from_entities("extract", (), note="没有任何任务需要执行"),
    )

    assert result.status is ResultStatus.SUCCESS
    assert captured == {"champion_ids": (), "map_ids": ()}


def _patch_main_runtime(
    monkeypatch,
    *,
    actions: list[str],
    source_mode: SourceMode = SourceMode.LOCAL_PATH,
):
    ctx = SimpleNamespace(
        config=SimpleNamespace(source_mode=source_mode),
        runtime_cache={},
        paths=SimpleNamespace(log_path=Path("logs")),
    )
    cleanup_calls: list[str] = []

    class FakeApp:
        def __init__(self, app_ctx) -> None:
            assert app_ctx is ctx

        def cleanup_remote_artifacts(self) -> None:
            cleanup_calls.append("cleanup")

    summary = SimpleNamespace(stage_context=lambda *_args, **_kwargs: nullcontext())
    monkeypatch.setattr(cli_module.sys, "argv", ["unpack", *actions])
    monkeypatch.setattr(cli_module, "initialize_app", lambda _args: ctx)
    monkeypatch.setattr(cli_module, "LolAudioUnpackApp", FakeApp)
    monkeypatch.setattr(cli_module, "get_or_create_run_summary", lambda _cache: summary)
    monkeypatch.setattr(cli_module, "attach_run_summary_sink", lambda _summary: None)
    monkeypatch.setattr(cli_module, "emit_cli_run_summary", lambda *_args, **_kwargs: None)
    return cleanup_calls


@pytest.mark.parametrize(
    ("status", "expected_exit"),
    [
        (ResultStatus.SUCCESS, EXIT_SUCCESS),
        (ResultStatus.PARTIAL, EXIT_PARTIAL),
        (ResultStatus.FAILED, EXIT_FAILED),
        (ResultStatus.CANCELLED, EXIT_CANCELLED),
    ],
)
def test_main_maps_typed_result_to_process_exit(monkeypatch, status: ResultStatus, expected_exit: int) -> None:
    cleanup_calls = _patch_main_runtime(monkeypatch, actions=["extract"])
    result = StageResult("extract", status=status)
    monkeypatch.setattr(cli_module, "run_extract", lambda *_args, **_kwargs: result)

    exit_code = cli_module.main()

    assert exit_code == expected_exit
    assert cleanup_calls == ["cleanup"]


def test_main_stops_dependent_stages_after_update_failure(monkeypatch) -> None:
    cleanup_calls = _patch_main_runtime(monkeypatch, actions=["update", "extract", "mapping"])
    monkeypatch.setattr(
        cli_module,
        "run_update",
        lambda *_args, **_kwargs: StageResult.from_error("update", OSError("boom")),
    )
    monkeypatch.setattr(
        cli_module, "run_extract", lambda *_args, **_kwargs: pytest.fail("update 失败后不得执行 extract")
    )
    monkeypatch.setattr(
        cli_module, "run_mapping", lambda *_args, **_kwargs: pytest.fail("update 失败后不得执行 mapping")
    )

    exit_code = cli_module.main()

    assert exit_code == EXIT_FAILED
    assert cleanup_calls == ["cleanup"]


def test_main_treats_missing_selected_stage_result_as_failure(monkeypatch) -> None:
    _patch_main_runtime(monkeypatch, actions=["extract"])
    monkeypatch.setattr(cli_module, "run_extract", lambda *_args, **_kwargs: None)

    assert cli_module.main() == EXIT_FAILED


def test_main_continues_independent_mapping_after_extract_partial(monkeypatch) -> None:
    _patch_main_runtime(monkeypatch, actions=["extract", "mapping"])
    calls: list[str] = []
    monkeypatch.setattr(
        cli_module,
        "run_extract",
        lambda *_args, **_kwargs: calls.append("extract") or _stage("extract", ResultStatus.PARTIAL),
    )
    monkeypatch.setattr(
        cli_module,
        "run_mapping",
        lambda *_args, **_kwargs: calls.append("mapping") or _stage("mapping"),
    )

    exit_code = cli_module.main()

    assert exit_code == EXIT_PARTIAL
    assert calls == ["extract", "mapping"]


def test_main_uses_remote_run_result_without_replaying_local_stages(monkeypatch) -> None:
    cleanup_calls = _patch_main_runtime(
        monkeypatch,
        actions=["extract"],
        source_mode=SourceMode.REMOTE_SNAPSHOT,
    )
    remote_result = cli_module.RunResult((_stage("extract", ResultStatus.PARTIAL),))
    monkeypatch.setattr(cli_module, "run_remote_workflow", lambda *_args, **_kwargs: remote_result)
    monkeypatch.setattr(cli_module, "run_extract", lambda *_args, **_kwargs: pytest.fail("不得重复执行本地 extract"))

    exit_code = cli_module.main()

    assert exit_code == EXIT_PARTIAL
    assert cleanup_calls == ["cleanup"]


def test_main_maps_input_error_and_keyboard_interrupt(monkeypatch) -> None:
    monkeypatch.setattr(cli_module.sys, "argv", ["unpack", "extract"])
    monkeypatch.setattr(
        cli_module,
        "_validate_config_argv",
        lambda _argv: (_ for _ in ()).throw(runtime_cli.CliInputError("bad input")),
    )
    assert cli_module.main() == EXIT_INPUT

    monkeypatch.setattr(cli_module, "_validate_config_argv", runtime_cli._validate_config_argv)
    cleanup_calls = _patch_main_runtime(monkeypatch, actions=["extract"])
    monkeypatch.setattr(cli_module, "run_extract", lambda *_args, **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt))

    assert cli_module.main() == EXIT_CANCELLED
    assert cleanup_calls == ["cleanup"]
