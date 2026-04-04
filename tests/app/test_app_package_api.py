"""`app/` 新公开入口测试。"""

from __future__ import annotations

import lol_audio_unpack.app as app_pkg
import lol_audio_unpack.app.context as app_context_pkg
import lol_audio_unpack.app.facade as app_facade_pkg
import lol_audio_unpack.app.remote as app_remote_pkg
import lol_audio_unpack.app.types as app_types_pkg
from lol_audio_unpack import app as root_app_pkg


def test_root_package_can_import_app_module() -> None:
    """根包应暴露新的 `app` 子包入口。"""
    assert root_app_pkg is app_pkg


def test_app_package_exports_context_contract() -> None:
    """`app` 包应暴露上下文相关公开类型与工厂。"""
    assert app_pkg.AppConfig is app_types_pkg.AppConfig
    assert app_pkg.AppContext is app_types_pkg.AppContext
    assert app_pkg.AppContextValidationError is app_types_pkg.AppContextValidationError
    assert app_pkg.AppPaths is app_types_pkg.AppPaths
    assert app_pkg.OperationOptions is app_types_pkg.OperationOptions
    assert app_pkg.RemoteSnapshotConfig is app_types_pkg.RemoteSnapshotConfig
    assert app_pkg.SourceMode is app_types_pkg.SourceMode
    assert app_pkg.WavOutputOptions is app_types_pkg.WavOutputOptions
    assert app_pkg.create_app_context is app_context_pkg.create_app_context


def test_app_package_exports_facade_contract() -> None:
    """`app` 包应暴露应用门面与 remote 类型。"""
    assert app_pkg.LolAudioUnpackApp is app_facade_pkg.LolAudioUnpackApp
    assert app_pkg.RemoteEntityWorkItem is app_remote_pkg.RemoteEntityWorkItem
    assert app_pkg.RemoteEntityCallbackPayload is app_remote_pkg.RemoteEntityCallbackPayload


def test_app_submodules_export_expected_symbols() -> None:
    """`app` 子模块应各自提供对应公开入口。"""
    assert callable(app_context_pkg.create_app_context)
    assert app_context_pkg.AppContext is app_types_pkg.AppContext
    assert app_facade_pkg.LolAudioUnpackApp is app_pkg.LolAudioUnpackApp
    assert app_remote_pkg.RemoteEntityWorkItem is app_pkg.RemoteEntityWorkItem
    assert app_remote_pkg.RemoteEntityCallbackPayload is app_pkg.RemoteEntityCallbackPayload
    assert app_types_pkg.AppConfig is app_pkg.AppConfig
    assert app_types_pkg.OperationOptions is app_pkg.OperationOptions
