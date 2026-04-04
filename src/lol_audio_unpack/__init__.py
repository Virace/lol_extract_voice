"""应用入口与运行时版本元数据导出。"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from .app import (
    AppConfig,
    AppContext,
    AppContextValidationError,
    AppPaths,
    LolAudioUnpackApp,
    OperationOptions,
    RemoteEntityCallbackPayload,
    RemoteEntityWorkItem,
    RemoteSnapshotConfig,
    SourceMode,
    create_app_context,
)
from .manager import BinUpdater, DataReader, DataUpdater
from .utils.logging import setup_logging
from .utils.versioning import resolve_runtime_version

_STATIC_VERSION = "3.5.1.dev0"
__version__ = resolve_runtime_version(Path(__file__).resolve().parents[2], _STATIC_VERSION)

logger.disable("lol_audio_unpack")


def setup_app(dev_mode: bool = False, log_level: str = "INFO", **kwargs) -> AppContext:
    """初始化应用并返回可注入上下文。

    Args:
        dev_mode: 是否开启开发模式。
        log_level: 日志级别，例如 ``INFO``、``DEBUG``。
        **kwargs: 透传给 ``create_app_context`` 的参数。

    Returns:
        初始化后的 ``AppContext``。
    """
    logger.enable("lol_audio_unpack")

    logger.remove()
    try:
        logger.add(sys.stdout, level=log_level.upper(), enqueue=True, colorize=True)
    except (OSError, PermissionError):
        logger.add(sys.stdout, level=log_level.upper(), enqueue=False, colorize=True)
        logger.warning("日志队列初始化失败，已回退为非 enqueue 模式。")

    app_context = create_app_context(dev_mode=dev_mode, **kwargs)

    setup_logging(
        dev_mode=dev_mode,
        log_level=log_level,
        log_file_path=app_context.paths.log_path,
        show_function_info=True,
    )

    logger.info("Application setup complete.")
    return app_context


__all__ = [
    "AppConfig",
    "AppContext",
    "AppContextValidationError",
    "AppPaths",
    "LolAudioUnpackApp",
    "OperationOptions",
    "RemoteEntityCallbackPayload",
    "RemoteEntityWorkItem",
    "RemoteSnapshotConfig",
    "SourceMode",
    "__version__",
    "setup_app",
    "BinUpdater",
    "DataUpdater",
    "DataReader",
]
