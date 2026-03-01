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


def test_execute_update_operations_all(monkeypatch):
    parser = cli.create_parser()
    args = parser.parse_args(["--update"])

    calls = {}

    class FakeDataUpdater:
        def __init__(self, force_update=False):
            calls["data_updater_force"] = force_update

        def check_and_update(self):
            calls["checked"] = True

    class FakeBinUpdater:
        def __init__(self, force_update=False, process_events=True):
            calls["bin_updater_init"] = (force_update, process_events)

        def update(self, target="all", champion_ids=None, map_ids=None):
            calls["bin_updater_update"] = (target, champion_ids, map_ids)

    monkeypatch.setattr(cli, "DataUpdater", FakeDataUpdater)
    monkeypatch.setattr(cli, "BinUpdater", FakeBinUpdater)

    cli.execute_update_operations(args)

    assert calls["data_updater_force"] is False
    assert calls["checked"] is True
    assert calls["bin_updater_init"] == (False, True)
    assert calls["bin_updater_update"] == ("all", None, None)


def test_execute_update_operations_targeted_champions(monkeypatch):
    parser = cli.create_parser()
    args = parser.parse_args(["--update-champions", "103,222, 1", "--force", "--skip-events"])

    calls = {}

    class FakeDataUpdater:
        def __init__(self, force_update=False):
            calls["data_updater_force"] = force_update

        def check_and_update(self):
            calls["checked"] = True

    class FakeBinUpdater:
        def __init__(self, force_update=False, process_events=True):
            calls["bin_updater_init"] = (force_update, process_events)

        def update(self, target="all", champion_ids=None, map_ids=None):
            calls["bin_updater_update"] = (target, champion_ids, map_ids)

    monkeypatch.setattr(cli, "DataUpdater", FakeDataUpdater)
    monkeypatch.setattr(cli, "BinUpdater", FakeBinUpdater)

    cli.execute_update_operations(args)

    assert calls["data_updater_force"] is True
    assert calls["checked"] is True
    assert calls["bin_updater_init"] == (True, False)
    assert calls["bin_updater_update"] == ("skin", ["103", "222", "1"], None)
