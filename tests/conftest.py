"""提供不依赖 GUI 的全局测试隔离夹具。"""

from collections.abc import Iterator
from pathlib import Path

import pytest

import lol_audio_unpack.app.context as app_context_module
import lol_audio_unpack.config.ini as config_ini_module
from lol_audio_unpack.manager.data_reader import DataReader
from lol_audio_unpack.utils.common import Singleton
from lol_audio_unpack.utils.runtime_paths import detect_runtime_paths


@pytest.fixture(autouse=True)
def _isolate_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """隔离配置目录与 ``DataReader`` 单例缓存。

    Args:
        monkeypatch: pytest 属性替换夹具。
        tmp_path: 当前测试的临时目录。

    Yields:
        测试执行控制权。
    """
    work_dir = tmp_path / "isolated_env"
    work_dir.mkdir(parents=True, exist_ok=True)

    # 强制把默认配置目录切换到临时目录，避免读取真实配置文件
    monkeypatch.setattr(
        app_context_module,
        "detect_runtime_paths",
        lambda: detect_runtime_paths(
            is_frozen=False,
            cwd=work_dir,
            executable=work_dir / "python.exe",
        ),
    )
    monkeypatch.setattr(
        config_ini_module,
        "detect_runtime_paths",
        lambda: detect_runtime_paths(
            is_frozen=False,
            cwd=work_dir,
            executable=work_dir / "python.exe",
        ),
    )

    Singleton._instances.pop(DataReader, None)

    yield

    Singleton._instances.pop(DataReader, None)
