"""配置包新入口测试。"""

from __future__ import annotations

from pathlib import Path

import lol_audio_unpack.config as config_pkg
import lol_audio_unpack.config.ini as config_ini_module
from lol_audio_unpack import config as root_config_pkg
from lol_audio_unpack.utils.runtime_paths import detect_runtime_paths


def test_root_package_can_import_config_module() -> None:
    """根包应暴露新的 ``config`` 子包入口。"""
    assert root_config_pkg is config_pkg


def test_config_package_exports_schema_symbols() -> None:
    """新配置包应暴露稳定的 schema 常量与类型。"""
    assert config_pkg.SettingKey.GAME_PATH == "GAME_PATH"
    assert config_pkg.ConfigSection.APP == "app"
    assert config_pkg.DEFAULT_REMOTE_LIVE_REGION == "EUW"
    assert callable(config_pkg.build_settings)
    assert config_pkg.SHARED_FIELDS_BY_KEY[config_pkg.SettingKey.GAME_PATH].ini_key == "game_path"
    assert config_pkg.SHARED_FIELDS_BY_INI_KEY["game_path"].key == config_pkg.SettingKey.GAME_PATH
    assert "game_path" in config_pkg.CONTEXT_OPTION_ATTRS


def test_config_package_round_trips_shared_settings(tmp_path: Path) -> None:
    """新入口应能独立完成共享配置的写回与读取。"""
    config_file = tmp_path / "lol-audio-unpack.ini"
    config_pkg.write_settings(
        config_file,
        {
            "GAME_PATH": str(tmp_path / "game"),
            "OUTPUT_PATH": str(tmp_path / "output"),
            "GROUP_BY_TYPE": True,
        },
    )

    loaded_settings = config_pkg.load_settings(config_file)

    assert loaded_settings == {
        "GAME_PATH": str(tmp_path / "game"),
        "OUTPUT_PATH": str(tmp_path / "output"),
        "GROUP_BY_TYPE": "true",
    }


def test_config_package_default_path_uses_runtime_config_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """新入口应直接使用 ``config.ini`` 模块自己的运行时路径探测。"""
    runtime_root = tmp_path / "runtime-root"
    runtime_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        config_ini_module,
        "detect_runtime_paths",
        lambda: detect_runtime_paths(
            is_frozen=False,
            cwd=runtime_root,
            executable=tmp_path / "python" / "python.exe",
        ),
    )

    config_file = config_pkg.resolve_default_path()

    assert config_file == runtime_root / "lol-audio-unpack.ini"
    assert config_file.parent == runtime_root


def test_config_package_keeps_short_public_api() -> None:
    assert callable(config_pkg.load_settings)
    assert callable(config_pkg.write_settings)
    assert callable(config_pkg.load_command_config)
    assert callable(config_pkg.write_command_config)
    assert callable(config_pkg.resolve_default_path)
