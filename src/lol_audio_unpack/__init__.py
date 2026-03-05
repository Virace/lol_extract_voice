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
    AppPaths,
    OperationOptions,
    build_app_context_from_legacy,
)
from .facade import LolAudioUnpackApp
from .manager import BinUpdater, DataReader, DataUpdater
from .utils.config import config
from .utils.logging import setup_logging

logger.disable("lol_audio_unpack")


def setup_app(dev_mode: bool = False, log_level: str = "INFO", **kwargs) -> AppContext:
    """初始化应用并返回可注入上下文。

    Args:
        dev_mode: 是否开启开发模式。
        log_level: 日志级别，例如 ``INFO``、``DEBUG``。
        **kwargs: 透传给 ``config.initialize`` 的参数。

    Returns:
        由当前配置构建的 ``AppContext``。
    """
    # 阶段一：启用此包的日志功能
    logger.enable("lol_audio_unpack")

    # 阶段二：初始化配置系统
    logger.remove()  # 移除所有默认的 handler
    logger.add(sys.stdout, level=log_level.upper(), enqueue=True, colorize=True)

    # 阶段三：初始化配置系统
    # 此时，所有 config 内部的日志都会遵循上面刚刚设置的级别
    config.initialize(dev_mode=dev_mode, **kwargs)

    # 阶段四：设置完整的日志系统

    log_path = config.get("LOG_PATH")
    setup_logging(
        dev_mode=dev_mode,
        log_level=log_level,
        log_file_path=log_path,
        show_function_info=True,  # 模块项目总是显示函数信息，便于调试
    )

    app_context = build_app_context_from_legacy(config)
    logger.info("Application setup complete.")
    return app_context


__all__ = [
    "AppConfig",
    "AppContext",
    "AppPaths",
    "LolAudioUnpackApp",
    "OperationOptions",
    "setup_app",
    "BinUpdater",
    "config",
    "DataUpdater",
    "DataReader",
]
