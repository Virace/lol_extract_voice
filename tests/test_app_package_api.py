"""`app/` 新公开入口测试。"""

from __future__ import annotations

import lol_audio_unpack.app as app_pkg
import lol_audio_unpack.app.context as app_context_pkg
import lol_audio_unpack.app.facade as app_facade_pkg
import lol_audio_unpack.app.remote as app_remote_pkg
import lol_audio_unpack.app.types as app_types_pkg
import lol_audio_unpack.app_context as legacy_context
import lol_audio_unpack.facade as legacy_facade
from lol_audio_unpack import app as root_app_pkg


def test_root_package_can_import_app_module() -> None:
    """根包应暴露新的 `app` 子包入口。"""
    assert root_app_pkg is app_pkg


def test_app_package_exports_context_contract() -> None:
    """`app` 包应暴露上下文相关公开类型与工厂。"""
    assert app_pkg.AppConfig is legacy_context.AppConfig
    assert app_pkg.AppContext is legacy_context.AppContext
    assert app_pkg.AppContextValidationError is legacy_context.AppContextValidationError
    assert app_pkg.AppPaths is legacy_context.AppPaths
    assert app_pkg.OperationOptions is legacy_context.OperationOptions
    assert app_pkg.RemoteSnapshotConfig is legacy_context.RemoteSnapshotConfig
    assert app_pkg.SourceMode is legacy_context.SourceMode
    assert app_pkg.WavOutputOptions is legacy_context.WavOutputOptions
    assert app_pkg.create_app_context is legacy_context.create_app_context


def test_app_package_exports_facade_contract() -> None:
    """`app` 包应暴露应用门面与 remote 类型。"""
    assert app_pkg.LolAudioUnpackApp is legacy_facade.LolAudioUnpackApp
    assert app_pkg.RemoteEntityWorkItem is legacy_facade.RemoteEntityWorkItem
    assert app_pkg.RemoteEntityCallbackPayload is legacy_facade.RemoteEntityCallbackPayload


def test_app_submodules_export_expected_symbols() -> None:
    """`app` 子模块应各自提供对应公开入口。"""
    assert app_context_pkg.create_app_context is legacy_context.create_app_context
    assert app_context_pkg.AppContext is legacy_context.AppContext
    assert app_facade_pkg.LolAudioUnpackApp is legacy_facade.LolAudioUnpackApp
    assert app_remote_pkg.RemoteEntityWorkItem is legacy_facade.RemoteEntityWorkItem
    assert app_remote_pkg.RemoteEntityCallbackPayload is legacy_facade.RemoteEntityCallbackPayload
    assert app_types_pkg.AppConfig is legacy_context.AppConfig
    assert app_types_pkg.OperationOptions is legacy_context.OperationOptions
