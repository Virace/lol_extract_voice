"""验证 runtime.remote 包公开导出面的回归测试。"""

from importlib import import_module

import pytest

pytestmark = pytest.mark.unit


def test_runtime_remote_exports_public_api() -> None:
    """验证 runtime.remote 导出了当前约定的公开对象。"""
    runtime_remote = import_module("lol_audio_unpack.runtime.remote")

    assert runtime_remote.__all__ == [
        "RemotePreparer",
        "LcuResult",
        "BinInputResult",
        "GameWadResult",
    ]


def test_remote_preparer_exposes_final_cleanup_method_only() -> None:
    """验证 runtime remote 入口只保留最终清理方法名。"""
    runtime_remote = import_module("lol_audio_unpack.runtime.remote")

    assert hasattr(runtime_remote.RemotePreparer, "cleanup_artifacts")
    assert not hasattr(runtime_remote.RemotePreparer, "cleanup_tracked_artifacts")
