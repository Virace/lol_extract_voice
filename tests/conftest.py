import os

import pytest


@pytest.fixture(autouse=True)
def _reset_config_state(monkeypatch):
    # 避免测试受到本地环境变量污染
    for key in list(os.environ):
        if key.startswith("LOL_"):
            monkeypatch.delenv(key, raising=False)

    from lol_audio_unpack.utils.config import Config, config as config_proxy

    Config.reset_instance()
    config_proxy._real_config = None
    config_proxy._default_env_path = None
    config_proxy._default_env_prefix = "LOL_"
    config_proxy._default_dev_mode = False

    yield

    Config.reset_instance()
    config_proxy._real_config = None
