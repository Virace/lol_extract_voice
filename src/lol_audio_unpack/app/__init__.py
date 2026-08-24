"""应用层公开入口。"""

from __future__ import annotations

from lol_audio_unpack.model.progress import OperationProgress

from .context import create_app_context
from .facade import LolAudioUnpackApp
from .resource_pack import ResourcePackWadRef
from .results import EntityResult, ResultStatus, RunResult, StageResult
from .types import (
    AppConfig,
    AppContext,
    AppContextValidationError,
    AppPaths,
    OperationOptions,
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
    "OperationProgress",
    "ResultStatus",
    "ResourcePackWadRef",
    "RunResult",
    "StageResult",
    "WavOutputOptions",
    "create_app_context",
]
