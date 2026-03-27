from __future__ import annotations

from pathlib import Path

from lol_audio_unpack.gui.common import gui_config as gui_config_module
from lol_audio_unpack.gui.common.gui_config import GuiConfig
from lol_audio_unpack.utils.runtime_paths import detect_runtime_paths


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


def _sample_path(tmp_path: Path, *parts: str) -> str:
    return str(tmp_path.joinpath(*parts))


def test_gui_config_to_app_context_overrides(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _use_fake_qsettings(monkeypatch)
    sample_game_path = _sample_path(tmp_path, "game-client")
    sample_output_path = _sample_path(tmp_path, "output-root")
    sample_wwiser_path = _sample_path(tmp_path, "tools", "wwiser.pyz")
    sample_vgmstream_path = _sample_path(tmp_path, "tools", "vgmstream-cli.exe")

    cfg = GuiConfig()
    cfg.source_mode = "remote_snapshot"
    cfg.game_path = sample_game_path
    cfg.output_path = sample_output_path
    cfg.game_region = "zh_CN"
    cfg.group_by_type = True
    cfg.remote_live_region = "KR"
    cfg.cleanup_remote = False
    cfg.snapshot_version = "14.1"
    cfg.snapshot_lcu_url = "https://example.com/lcu"
    cfg.snapshot_game_url = "https://example.com/game"
    cfg.wwiser_path = sample_wwiser_path
    cfg.vgmstream_path = sample_vgmstream_path

    assert cfg.to_app_context_overrides() == {
        "SOURCE_MODE": "remote_snapshot",
        "GAME_PATH": sample_game_path,
        "OUTPUT_PATH": sample_output_path,
        "GAME_REGION": "zh_CN",
        "GROUP_BY_TYPE": True,
        "REMOTE_LIVE_REGION": "KR",
        "CLEANUP_REMOTE": False,
        "REMOTE_VERSION": "14.1",
        "REMOTE_LCU_MANIFEST_URL": "https://example.com/lcu",
        "REMOTE_GAME_MANIFEST_URL": "https://example.com/game",
        "WWISER_PATH": sample_wwiser_path,
    }


def test_gui_config_load_migrates_legacy_vgmstream_env_key(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _use_fake_qsettings(monkeypatch)
    sample_output_path = _sample_path(tmp_path, "output-root")
    sample_vgmstream_path = _sample_path(tmp_path, "tools", "vgmstream-cli.exe")

    env_file = Path(tmp_path) / ".lol.env"
    env_file.write_text(
        f"LOL_OUTPUT_PATH='{sample_output_path}'\n"
        f"LOL_VGMSTREAM_PATH='{sample_vgmstream_path}'\n",
        encoding="utf-8",
    )

    cfg = GuiConfig()
    cfg.load()

    assert cfg.output_path == sample_output_path
    assert cfg.vgmstream_path == sample_vgmstream_path
    assert FakeQSettings._store["vgmstream_path"] == sample_vgmstream_path
    assert "LOL_VGMSTREAM_PATH" not in env_file.read_text(encoding="utf-8")

    reloaded_cfg = GuiConfig()
    reloaded_cfg.load()

    assert reloaded_cfg.vgmstream_path == sample_vgmstream_path


def test_gui_config_save_keeps_vgmstream_in_qsettings_only(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _use_fake_qsettings(monkeypatch)
    sample_game_path = _sample_path(tmp_path, "game-client")
    sample_output_path = _sample_path(tmp_path, "output-root")
    sample_vgmstream_path = _sample_path(tmp_path, "tools", "vgmstream-cli.exe")

    cfg = GuiConfig()
    cfg.source_mode = "local_path"
    cfg.game_path = sample_game_path
    cfg.output_path = sample_output_path
    cfg.vgmstream_path = sample_vgmstream_path

    cfg.save()

    env_text = (Path(tmp_path) / ".lol.env").read_text(encoding="utf-8")
    assert "LOL_SOURCE_MODE='local_path'" in env_text
    assert f"LOL_OUTPUT_PATH='{sample_output_path}'" in env_text
    assert "LOL_VGMSTREAM_PATH" not in env_text
    assert FakeQSettings._store["vgmstream_path"] == sample_vgmstream_path


def test_gui_config_uses_runtime_config_root(monkeypatch, tmp_path):
    _use_fake_qsettings(monkeypatch)
    runtime_root = tmp_path / "runtime-root"
    runtime_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        gui_config_module,
        "detect_runtime_paths",
        lambda: detect_runtime_paths(
            is_frozen=True,
            cwd=tmp_path / "shortcut-workdir",
            executable=runtime_root / "LolAudioUnpack.exe",
        ),
    )

    cfg = GuiConfig()

    assert cfg._env_file == runtime_root / ".lol.env"


def test_gui_config_loads_legacy_smooth_scroll_into_split_flags(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _use_fake_qsettings(monkeypatch)

    FakeQSettings._store["smooth_scroll_enabled"] = True

    cfg = GuiConfig()
    cfg.load()

    assert cfg.page_smooth_scroll_enabled is True
    assert cfg.widget_smooth_scroll_enabled is True
    assert cfg.smooth_scroll_enabled is True


def test_gui_config_persists_split_smooth_scroll_flags(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _use_fake_qsettings(monkeypatch)

    cfg = GuiConfig()
    cfg.page_smooth_scroll_enabled = True
    cfg.widget_smooth_scroll_enabled = False
    cfg.save()

    assert FakeQSettings._store["page_smooth_scroll_enabled"] is True
    assert FakeQSettings._store["widget_smooth_scroll_enabled"] is False
    assert FakeQSettings._store["smooth_scroll_enabled"] is False

    reloaded_cfg = GuiConfig()
    reloaded_cfg.load()

    assert reloaded_cfg.page_smooth_scroll_enabled is True
    assert reloaded_cfg.widget_smooth_scroll_enabled is False
    assert reloaded_cfg.smooth_scroll_enabled is False


def test_gui_config_persists_log_drawer_auto_collapse_flag(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _use_fake_qsettings(monkeypatch)

    cfg = GuiConfig()
    cfg.log_drawer_auto_collapse_enabled = False
    cfg.save()

    assert FakeQSettings._store["log_drawer_auto_collapse_enabled"] is False

    reloaded_cfg = GuiConfig()
    reloaded_cfg.load()

    assert reloaded_cfg.log_drawer_auto_collapse_enabled is False


def test_gui_config_persists_log_levels(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _use_fake_qsettings(monkeypatch)
    monkeypatch.setattr(gui_config_module, "set_key", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gui_config_module, "unset_key", lambda *_args, **_kwargs: None)

    cfg = GuiConfig()
    cfg.console_log_level = "DEBUG"
    cfg.file_log_level = "TRACE"
    cfg.save()

    assert FakeQSettings._store["console_log_level"] == "DEBUG"
    assert FakeQSettings._store["file_log_level"] == "TRACE"

    reloaded_cfg = GuiConfig()
    reloaded_cfg.load()

    assert reloaded_cfg.console_log_level == "DEBUG"
    assert reloaded_cfg.file_log_level == "TRACE"
