# 🐍 Although never is often better than *right* now.
# 🐼 然而不假思索还不如不做
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2024/9/3 10:14
# @Update  : 2025/8/5 8:06
# @Detail  : lol_audio_unpack


__version__ = "3.5.1.dev0+test"

import sys

from loguru import logger

from .app_context import (
    AppConfig,
    AppContext,
    AppContextValidationError,
    AppPaths,
    OperationOptions,
    RemoteSnapshotConfig,
    SourceMode,
    create_app_context,
)
from .facade import LolAudioUnpackApp
from .manager import BinUpdater, DataReader, DataUpdater
from .utils.logging import setup_logging

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
    logger.add(sys.stdout, level=log_level.upper(), enqueue=True, colorize=True)

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
    "RemoteSnapshotConfig",
    "SourceMode",
    "setup_app",
    "BinUpdater",
    "DataUpdater",
    "DataReader",
]
