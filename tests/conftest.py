import os

import pytest

import lol_audio_unpack.app_context as app_context_module
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

    # 强制把默认配置目录切换到临时目录，避免读取项目根目录 .lol.env*
    monkeypatch.setattr(
        app_context_module,
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
