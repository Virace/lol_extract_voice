from __future__ import annotations

from pathlib import Path

from lol_audio_unpack.gui.common import gui_config as gui_config_module
from lol_audio_unpack.gui.common.gui_config import GuiConfig


class FakeQSettings:
    class Format:
        IniFormat = object()

    class Scope:
        UserScope = object()

    _store: dict[str, str] = {}

    def __init__(self, *args, **kwargs) -> None:
        _ = args, kwargs

    def value(self, key: str, default=None):
        return self._store.get(key, default)

    def setValue(self, key: str, value) -> None:
        self._store[key] = value


def _use_fake_qsettings(monkeypatch) -> None:
    FakeQSettings._store = {}
    monkeypatch.setattr(gui_config_module, "QSettings", FakeQSettings)


def test_gui_config_to_app_context_overrides(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _use_fake_qsettings(monkeypatch)

    cfg = GuiConfig()
    cfg.source_mode = "remote_snapshot"
    cfg.game_path = r"D:\Games\League of Legends"
    cfg.output_path = r"E:\Temp\lol"
    cfg.game_region = "zh_CN"
    cfg.group_by_type = True
    cfg.remote_live_region = "KR"
    cfg.cleanup_remote = False
    cfg.snapshot_version = "14.1"
    cfg.snapshot_lcu_url = "https://example.com/lcu"
    cfg.snapshot_game_url = "https://example.com/game"
    cfg.wwiser_path = r"C:\tools\wwiser.pyz"
    cfg.vgmstream_path = r"C:\tools\vgmstream-cli.exe"

    assert cfg.to_app_context_overrides() == {
        "SOURCE_MODE": "remote_snapshot",
        "GAME_PATH": r"D:\Games\League of Legends",
        "OUTPUT_PATH": r"E:\Temp\lol",
        "GAME_REGION": "zh_CN",
        "GROUP_BY_TYPE": True,
        "REMOTE_LIVE_REGION": "KR",
        "CLEANUP_REMOTE": False,
        "REMOTE_VERSION": "14.1",
        "REMOTE_LCU_MANIFEST_URL": "https://example.com/lcu",
        "REMOTE_GAME_MANIFEST_URL": "https://example.com/game",
        "WWISER_PATH": r"C:\tools\wwiser.pyz",
    }


def test_gui_config_load_migrates_legacy_vgmstream_env_key(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _use_fake_qsettings(monkeypatch)

    env_file = Path(tmp_path) / ".lol.env"
    env_file.write_text(
        "LOL_OUTPUT_PATH='E:\\Temp\\lol'\n"
        "LOL_VGMSTREAM_PATH='C:\\tools\\vgmstream-cli.exe'\n",
        encoding="utf-8",
    )

    cfg = GuiConfig()
    cfg.load()

    assert cfg.output_path == r"E:\Temp\lol"
    assert cfg.vgmstream_path == r"C:\tools\vgmstream-cli.exe"
    assert FakeQSettings._store["vgmstream_path"] == r"C:\tools\vgmstream-cli.exe"
    assert "LOL_VGMSTREAM_PATH" not in env_file.read_text(encoding="utf-8")

    reloaded_cfg = GuiConfig()
    reloaded_cfg.load()

    assert reloaded_cfg.vgmstream_path == r"C:\tools\vgmstream-cli.exe"


def test_gui_config_save_keeps_vgmstream_in_qsettings_only(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _use_fake_qsettings(monkeypatch)

    cfg = GuiConfig()
    cfg.source_mode = "local_path"
    cfg.game_path = r"D:\Games\League of Legends"
    cfg.output_path = r"E:\Temp\lol"
    cfg.vgmstream_path = r"C:\tools\vgmstream-cli.exe"

    cfg.save()

    env_text = (Path(tmp_path) / ".lol.env").read_text(encoding="utf-8")
    assert "LOL_SOURCE_MODE='local_path'" in env_text
    assert "LOL_OUTPUT_PATH='E:\\Temp\\lol'" in env_text
    assert "LOL_VGMSTREAM_PATH" not in env_text
    assert FakeQSettings._store["vgmstream_path"] == r"C:\tools\vgmstream-cli.exe"
