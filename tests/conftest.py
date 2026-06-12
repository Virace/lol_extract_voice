import os

import pytest

import lol_audio_unpack.app.context as app_context_impl
import lol_audio_unpack.config.ini as config_ini_module
from lol_audio_unpack.gui.common import gui_config as gui_config_module
from lol_audio_unpack.manager.data_reader import DataReader
from lol_audio_unpack.utils.common import Singleton
from lol_audio_unpack.utils.runtime_paths import detect_runtime_paths


@pytest.fixture(autouse=True)
def _reset_config_state(monkeypatch, tmp_path):
    # 避免测试受到本地环境变量污染
    for key in list(os.environ):
        if key.startswith("LOL_"):
            monkeypatch.delenv(key, raising=False)

    isolated_work_dir = tmp_path / "isolated_env"
    isolated_work_dir.mkdir(parents=True, exist_ok=True)

    # 强制把默认配置目录切换到临时目录，避免读取真实配置文件
    monkeypatch.setattr(
        app_context_impl,
        "detect_runtime_paths",
        lambda: detect_runtime_paths(
            is_frozen=False,
            cwd=isolated_work_dir,
            executable=isolated_work_dir / "python.exe",
        ),
    )
    monkeypatch.setattr(
        config_ini_module,
        "detect_runtime_paths",
        lambda: detect_runtime_paths(
            is_frozen=False,
            cwd=isolated_work_dir,
            executable=isolated_work_dir / "python.exe",
        ),
    )
    monkeypatch.setattr(
        gui_config_module,
        "detect_runtime_paths",
        lambda: detect_runtime_paths(
            is_frozen=False,
            cwd=isolated_work_dir,
            executable=isolated_work_dir / "python.exe",
        ),
    )

    Singleton._instances.pop(DataReader, None)

    yield

    Singleton._instances.pop(DataReader, None)
