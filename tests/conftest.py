import os

import pytest

import lol_audio_unpack.app_context as app_context_module
import lol_audio_unpack.config_loading as config_loading_module
from lol_audio_unpack.gui.common import gui_config as gui_config_module
from lol_audio_unpack.manager.data_reader import DataReader
from lol_audio_unpack.utils.common import Singleton
from lol_audio_unpack.utils.runtime_paths import detect_runtime_paths


class FakeQSettings:
    """测试环境使用的内存版 QSettings 替身。"""

    class Format:
        IniFormat = object()

    class Scope:
        UserScope = object()

    _store: dict[str, object] = {}

    def __init__(self, *args, **kwargs) -> None:
        _ = args, kwargs

    def value(self, key: str, default=None):
        return self._store.get(key, default)

    def setValue(self, key: str, value) -> None:
        self._store[key] = value


@pytest.fixture(autouse=True)
def _reset_config_state(monkeypatch, tmp_path):
    # 避免测试受到本地环境变量污染
    for key in list(os.environ):
        if key.startswith("LOL_"):
            monkeypatch.delenv(key, raising=False)

    isolated_work_dir = tmp_path / "isolated_env"
    isolated_work_dir.mkdir(parents=True, exist_ok=True)
    FakeQSettings._store = {}

    # 强制把默认配置目录切换到临时目录，避免读取真实配置文件
    monkeypatch.setattr(
        app_context_module,
        "detect_runtime_paths",
        lambda: detect_runtime_paths(
            is_frozen=False,
            cwd=isolated_work_dir,
            executable=isolated_work_dir / "python.exe",
        ),
    )
    monkeypatch.setattr(
        config_loading_module,
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
    monkeypatch.setattr(gui_config_module, "QSettings", FakeQSettings)

    Singleton._instances.pop(DataReader, None)

    yield

    Singleton._instances.pop(DataReader, None)
