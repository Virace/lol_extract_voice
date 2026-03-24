from pathlib import Path
from types import SimpleNamespace

import pytest

import lol_audio_unpack.__main__ as cli
from lol_audio_unpack.app_context import SourceMode

pytestmark = pytest.mark.unit


def test_parse_ids():
    assert cli.parse_ids(None) is None
    assert cli.parse_ids("all") is None
    assert cli.parse_ids("1,2, 3 , ,") == ["1", "2", "3"]


def test_validate_args_requires_at_least_one_action():
    parser = cli.create_parser()
    args = parser.parse_args([])

    with pytest.raises(SystemExit) as exc:
        cli.validate_args(args, parser)

    assert exc.value.code == 1


def test_validate_args_integrate_data_requires_mapping():
    parser = cli.create_parser()
    args = parser.parse_args(["--update", "--integrate-data"])

    with pytest.raises(SystemExit) as exc:
        cli.validate_args(args, parser)

    assert exc.value.code == 1


def test_validate_args_integrate_data_with_mapping_allowed():
    parser = cli.create_parser()
    args = parser.parse_args(["--mapping", "--integrate-data"])

    cli.validate_args(args, parser)


def test_execute_update_operations_all():
    parser = cli.create_parser()
    args = parser.parse_args(["--update"])

    calls = {}

    class FakeApp:
        def update(self, opts, *, target="all"):
            calls["target"] = target
            calls["opts"] = opts

    cli.execute_update_operations(args, FakeApp())

    assert calls["target"] == "all"
    assert calls["opts"].force_update is False
    assert calls["opts"].process_events is True
    assert calls["opts"].champion_ids is None
    assert calls["opts"].map_ids is None


def test_execute_update_operations_targeted_champions():
    parser = cli.create_parser()
    args = parser.parse_args(["--update-champions", "103,222, 1", "--force", "--skip-events"])

    calls = {}

    class FakeApp:
        def update(self, opts, *, target="all"):
            calls["target"] = target
            calls["opts"] = opts

    cli.execute_update_operations(args, FakeApp())

    assert calls["target"] == "skin"
    assert calls["opts"].force_update is True
    assert calls["opts"].process_events is False
    assert calls["opts"].champion_ids == (103, 222, 1)


def test_execute_mapping_operations_defaults_to_native_hirc_without_wwiser():
    parser = cli.create_parser()
    args = parser.parse_args(["--mapping"])

    calls = {}

    class FakeApp:
        def mapping(self, opts, **kwargs):
            calls["opts"] = opts
            calls["kwargs"] = kwargs

    cli.execute_mapping_operations(args, FakeApp())

    assert calls["opts"].champion_ids is None
    assert calls["opts"].map_ids is None
    assert calls["opts"].integrate_data is False
    assert calls["kwargs"] == {}


def test_execute_mapping_operations_resolves_champion_aliases():
    parser = cli.create_parser()
    args = parser.parse_args(["--mapping-champions", "Annie,Ahri"])

    calls = []

    class FakeApp:
        def prepare_update_data(self, *, force_update=False):
            calls.append(("prepare", force_update))

        def resolve_champion_ids(self, selectors):
            calls.append(("resolve", tuple(selectors)))
            return (1, 103)

        def mapping(self, opts, **kwargs):
            calls.append(("mapping", opts.champion_ids, kwargs))

    cli.execute_mapping_operations(args, FakeApp())

    assert calls == [
        ("prepare", False),
        ("resolve", ("Annie", "Ahri")),
        ("mapping", (1, 103), {"include_maps": False}),
    ]


def test_execute_mapping_operations_invalid_selector_does_not_show_wwiser_hint(monkeypatch):
    parser = cli.create_parser()
    args = parser.parse_args(["--mapping-champions", "1,Ahri"])
    errors: list[str] = []

    monkeypatch.setattr(cli, "logger", SimpleNamespace(error=errors.append, info=lambda *_args, **_kwargs: None))

    cli.execute_mapping_operations(args, SimpleNamespace())

    assert any("构建英雄映射失败" in message for message in errors)
    assert all("WWISER_PATH" not in message for message in errors)


def test_execute_mapping_operations_invalid_wwiser_path_shows_native_hint(monkeypatch):
    parser = cli.create_parser()
    missing_wwiser_path = str(Path("missing") / "wwiser.pyz")
    args = parser.parse_args(["--mapping", "--wwiser-path", missing_wwiser_path])
    errors: list[str] = []

    monkeypatch.setattr(
        cli,
        "logger",
        SimpleNamespace(
            error=errors.append,
            info=lambda *_args, **_kwargs: None,
            success=lambda *_args, **_kwargs: None,
        ),
    )

    class FakeApp:
        def mapping(self, _opts, **_kwargs):
            raise ValueError(f"错误：Wwiser 工具路径不存在或不是文件: {missing_wwiser_path}")

    with pytest.raises(SystemExit) as exc:
        cli.execute_mapping_operations(args, FakeApp())

    assert exc.value.code == 1
    assert any("默认 NativeHIRC" in message for message in errors)
    assert any("WWISER_PATH" in message for message in errors)


def test_build_cli_overrides_only_keeps_explicit_values():
    parser = cli.create_parser()
    sample_game_path = str(Path("samples") / "game")
    sample_output_path = str(Path("samples") / "output")
    args = parser.parse_args(
        [
            "--update",
            "--game-path",
            sample_game_path,
            "--output-path",
            sample_output_path,
            "--exclude-type",
            "MUSIC",
            "--no-group-by-type",
        ]
    )

    overrides = cli.build_cli_overrides(args)

    assert overrides == {
        "GAME_PATH": sample_game_path,
        "OUTPUT_PATH": sample_output_path,
        "EXCLUDE_TYPE": "MUSIC",
        "GROUP_BY_TYPE": False,
    }


def test_build_cli_overrides_includes_with_bp_vo_when_explicit():
    parser = cli.create_parser()
    args = parser.parse_args(["--update", "--with-bp-vo"])

    overrides = cli.build_cli_overrides(args)

    assert overrides == {"WITH_BP_VO": True}


def test_build_cli_overrides_includes_cleanup_remote_when_explicit():
    parser = cli.create_parser()
    args = parser.parse_args(["--update", "--no-cleanup-remote"])

    overrides = cli.build_cli_overrides(args)

    assert overrides == {"CLEANUP_REMOTE": False}


def test_initialize_app_passes_cli_overrides_to_setup_app(monkeypatch, tmp_path):
    parser = cli.create_parser()
    game_path = tmp_path / "game"
    game_path.mkdir(parents=True, exist_ok=True)

    args = parser.parse_args(
        [
            "--update",
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

    monkeypatch.setattr(cli, "setup_app", fake_setup_app)

    ctx = cli.initialize_app(args)

    assert captured["dev_mode"] is False
    assert captured["log_level"] == "INFO"
    assert ctx == fake_context
    assert captured["kwargs"]["cli_overrides"] == {
        "GAME_PATH": str(game_path),
        "OUTPUT_PATH": str(tmp_path / "output"),
        "GAME_REGION": "en_US",
        "EXCLUDE_TYPE": "VO",
        "WWISER_PATH": str(tmp_path / "wwiser.pyz"),
        "GROUP_BY_TYPE": True,
    }


def test_initialize_app_allows_missing_remote_snapshot_game_path(monkeypatch, tmp_path):
    parser = cli.create_parser()
    args = parser.parse_args(["--update"])

    fake_context = SimpleNamespace(
        config=SimpleNamespace(
            game_path=tmp_path / "remote-game",
            source_mode=SourceMode.REMOTE_SNAPSHOT,
        )
    )

    monkeypatch.setattr(cli, "setup_app", lambda **_kwargs: fake_context)

    ctx = cli.initialize_app(args)

    assert ctx == fake_context


def test_initialize_app_exits_when_config_validation_fails(monkeypatch):
    parser = cli.create_parser()
    args = parser.parse_args(["--update"])

    def fake_setup_app(*, dev_mode=False, log_level="INFO", **kwargs):
        raise cli.AppContextValidationError("缺少必要的配置项: GAME_PATH, OUTPUT_PATH")

    monkeypatch.setattr(cli, "setup_app", fake_setup_app)

    with pytest.raises(SystemExit) as exc:
        cli.initialize_app(args)

    assert exc.value.code == 1


def test_parse_int_ids():
    assert cli.parse_int_ids(None) is None
    assert cli.parse_int_ids("all") is None
    assert cli.parse_int_ids("1,2, 3") == (1, 2, 3)


def test_resolve_cli_champion_ids_supports_aliases():
    calls = []

    class FakeApp:
        def prepare_update_data(self, *, force_update=False):
            calls.append(("prepare", force_update))

        def resolve_champion_ids(self, selectors):
            calls.append(("resolve", tuple(selectors)))
            return (1, 103)

    champion_ids = cli.resolve_cli_champion_ids("Annie,Ahri", app=FakeApp())

    assert champion_ids == (1, 103)
    assert calls == [("prepare", False), ("resolve", ("Annie", "Ahri"))]


def test_resolve_cli_champion_ids_rejects_mixed_selectors():
    with pytest.raises(ValueError, match="混用 ID 与 alias"):
        cli.resolve_cli_champion_ids("1,Ahri", app=SimpleNamespace())


def test_execute_remote_entity_workflow_delegates_to_facade(monkeypatch):
    args = SimpleNamespace(
        update=False,
        update_champions=None,
        update_maps=None,
        extract=False,
        extract_champions="1,103",
        extract_maps=None,
        mapping=False,
        mapping_champions="103",
        mapping_maps=None,
        max_workers=4,
        force=False,
        skip_events=False,
        integrate_data=False,
    )

    captured = {}

    def fake_run_remote_entity_workflow(**kwargs):
        captured.update(kwargs)

    app = SimpleNamespace(run_remote_entity_workflow=fake_run_remote_entity_workflow)

    cli.execute_remote_entity_workflow(args, app)

    assert captured["update_options"] is None
    assert captured["update_target"] == "all"
    assert captured["extract_options"].champion_ids == (1, 103)
    assert captured["extract_options"].map_ids is None
    assert captured["mapping_options"].champion_ids == (103,)
    assert captured["mapping_options"].map_ids is None
    assert captured["extract_include_champions"] is True
    assert captured["extract_include_maps"] is False
    assert captured["mapping_include_champions"] is True
    assert captured["mapping_include_maps"] is False


def test_execute_update_operations_resolves_champion_aliases():
    parser = cli.create_parser()
    args = parser.parse_args(["--update-champions", "Annie,Ahri"])

    calls = []

    class FakeApp:
        def prepare_update_data(self, *, force_update=False):
            calls.append(("prepare", force_update))

        def resolve_champion_ids(self, selectors):
            calls.append(("resolve", tuple(selectors)))
            return (1, 103)

        def update(self, opts, *, target="all"):
            calls.append(("update", target, opts.champion_ids))

    cli.execute_update_operations(args, FakeApp())

    assert calls == [
        ("prepare", False),
        ("resolve", ("Annie", "Ahri")),
        ("update", "skin", (1, 103)),
    ]
