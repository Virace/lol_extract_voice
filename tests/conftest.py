import os

import pytest

import lol_audio_unpack.utils.config as config_module
from lol_audio_unpack.manager.data_reader import DataReader
from lol_audio_unpack.utils.common import Singleton
from lol_audio_unpack.utils.config import Config
from lol_audio_unpack.utils.config import config as config_proxy


@pytest.fixture(autouse=True)
def _reset_config_state(monkeypatch, tmp_path):
    # 避免测试受到本地环境变量污染
    for key in list(os.environ):
        if key.startswith("LOL_"):
            monkeypatch.delenv(key, raising=False)

    isolated_work_dir = tmp_path / "isolated_env"
    isolated_work_dir.mkdir(parents=True, exist_ok=True)

    # 强制把默认配置目录切换到临时目录，避免读取项目根目录 .lol.env*
    monkeypatch.setattr(config_module, "WORK_DIR", isolated_work_dir)

    Config.reset_instance()
    Singleton._instances.pop(DataReader, None)
    config_proxy._real_config = None
    config_proxy._default_env_path = isolated_work_dir
    config_proxy._default_env_prefix = "LOL_"
    config_proxy._default_dev_mode = False

    yield

    Config.reset_instance()
    Singleton._instances.pop(DataReader, None)
    config_proxy._real_config = None
