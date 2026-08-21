"""应用层公开入口。"""

from __future__ import annotations

from .context import create_app_context
from .facade import LolAudioUnpackApp
from .remote import RemoteEntityCallbackPayload, RemoteEntityWorkItem
from .resource_pack import ResourcePackWadRef
from .results import EntityResult, ResultStatus, RunResult, StageResult
from .types import (
    AppConfig,
    AppContext,
    AppContextValidationError,
    AppPaths,
    OperationOptions,
    RemoteSnapshotConfig,
    SourceMode,
    WavOutputOptions,
)

__all__ = [
    "AppConfig",
    "AppContext",
    "AppContextValidationError",
    "AppPaths",
    "EntityResult",
    "LolAudioUnpackApp",
    "OperationOptions",
    "RemoteEntityCallbackPayload",
    "RemoteEntityWorkItem",
    "RemoteSnapshotConfig",
    "ResultStatus",
    "ResourcePackWadRef",
    "RunResult",
    "SourceMode",
    "StageResult",
    "WavOutputOptions",
    "create_app_context",
]
