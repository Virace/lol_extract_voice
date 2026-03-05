from types import SimpleNamespace

import pytest

import lol_audio_unpack.__main__ as cli

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


def test_build_cli_overrides_only_keeps_explicit_values():
    parser = cli.create_parser()
    args = parser.parse_args(
        [
            "--update",
            "--game-path",
            "/tmp/game",
            "--output-path",
            "/tmp/output",
            "--exclude-type",
            "MUSIC",
            "--no-group-by-type",
        ]
    )

    overrides = cli.build_cli_overrides(args)

    assert overrides == {
        "GAME_PATH": "/tmp/game",
        "OUTPUT_PATH": "/tmp/output",
        "EXCLUDE_TYPE": "MUSIC",
        "GROUP_BY_TYPE": False,
    }


def test_build_cli_overrides_includes_with_bp_vo_when_explicit():
    parser = cli.create_parser()
    args = parser.parse_args(["--update", "--with-bp-vo"])

    overrides = cli.build_cli_overrides(args)

    assert overrides == {"WITH_BP_VO": True}


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
    fake_context = SimpleNamespace(config=SimpleNamespace(game_path=game_path))

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
