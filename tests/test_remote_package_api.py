"""验证 remote 包公开导出面的回归测试。"""

from importlib import import_module

import pytest

pytestmark = pytest.mark.unit


def test_remote_package_exports_remote_preparer_public_api() -> None:
    """验证 remote 包导出了当前约定的公开对象。"""
    remote_package = import_module("lol_audio_unpack.remote")

    assert remote_package.__all__ == [
        "RemoteSnapshotPreparer",
        "LcuPrepareResult",
        "BinInputPrepareResult",
        "GameWadPrepareResult",
    ]


def test_remote_package_and_implementation_module_share_public_objects() -> None:
    """验证包导出与实现模块导出指向同一公开对象。"""
    remote_package = import_module("lol_audio_unpack.remote")
    implementation_module = import_module("lol_audio_unpack.remote.preparer")

    for name in remote_package.__all__:
        assert getattr(remote_package, name) is getattr(implementation_module, name)

    assert implementation_module.__all__ == remote_package.__all__


def test_remote_preparer_exposes_final_cleanup_method_only() -> None:
    """验证远端准备器只保留最终清理方法名。"""
    remote_package = import_module("lol_audio_unpack.remote")

    assert hasattr(remote_package.RemoteSnapshotPreparer, "cleanup_artifacts")
    assert not hasattr(remote_package.RemoteSnapshotPreparer, "cleanup_tracked_artifacts")
