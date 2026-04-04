"""验证 runtime remote 包公开导出面的回归测试。"""

from importlib import import_module

import pytest

pytestmark = pytest.mark.unit


def test_runtime_package_exports_remote_public_api() -> None:
    """验证 runtime 顶层导出了 remote 公开对象。"""
    runtime_package = import_module("lol_audio_unpack.runtime")
    runtime_remote = import_module("lol_audio_unpack.runtime.remote")

    expected_remote_exports = [
        "RemoteSnapshotPreparer",
        "LcuPrepareResult",
        "BinInputPrepareResult",
        "GameWadPrepareResult",
    ]
    for name in expected_remote_exports:
        assert name in runtime_package.__all__
        assert getattr(runtime_package, name) is getattr(runtime_remote, name)


def test_legacy_remote_package_is_runtime_shim() -> None:
    """验证旧 remote 包入口只是 runtime.remote 的兼容层。"""
    legacy_remote = import_module("lol_audio_unpack.remote")
    runtime_remote = import_module("lol_audio_unpack.runtime.remote")

    assert legacy_remote.__all__ == runtime_remote.__all__
    for name in runtime_remote.__all__:
        assert getattr(legacy_remote, name) is getattr(runtime_remote, name)


def test_remote_preparer_exposes_final_cleanup_method_only() -> None:
    """验证 runtime remote 入口只保留最终清理方法名。"""
    runtime_remote = import_module("lol_audio_unpack.runtime.remote")

    assert hasattr(runtime_remote.RemoteSnapshotPreparer, "cleanup_artifacts")
    assert not hasattr(runtime_remote.RemoteSnapshotPreparer, "cleanup_tracked_artifacts")
