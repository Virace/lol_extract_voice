# 🐍 Although never is often better than *right* now.
# 🐼 然而不假思索还不如不做
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2024/9/3 10:14
# @Update  : 2025/8/1 1:13
# @Detail  : lol_audio_unpack


__version__ = "3.0.0-lite"

import sys
from pathlib import Path

from loguru import logger

from .manager import BinUpdater, DataReader, DataUpdater
from .utils.config import config


def setup_app(dev_mode: bool = False, log_level: str = "INFO", **kwargs):
    """
    初始化整个应用程序环境，包括配置和日志。
    这是所有外部调用的唯一推荐入口。

    :param dev_mode: 是否开启开发模式
    :param log_level: 日志级别 (e.g., "INFO", "DEBUG", "WARNING")
    :param kwargs: 其他传递给 config.initialize 的参数
    """
    # 阶段一：根据明确的参数，首先设置日志系统
    logger.remove()  # 移除所有默认的 handler
    logger.add(sys.stdout, level=log_level.upper(), enqueue=True, colorize=True)

    # 阶段二：初始化配置系统
    # 此时，所有 config 内部的日志都会遵循上面刚刚设置的级别
    config.initialize(dev_mode=dev_mode, **kwargs)

    # 阶段三 (可选): 添加文件日志
    log_path = config.get("LOG_PATH")
    if log_path:
        Path(log_path).mkdir(parents=True, exist_ok=True)
        # 文件日志通常记录更详细的信息
        # 文件名格式: YYYY-MM-DD_HH-mm-ss.log，保留最近10份日志文件
        logger.add(
            Path(log_path) / "{time:YYYY-MM-DD_HH-mm-ss}.log",
            rotation="100 MB",  # 当文件达到100MB时轮转
            retention=10,  # 保留最近10份日志文件
            level="DEBUG",
            enqueue=True,  # 确保文件日志也是线程安全的
        )

    logger.info("Application setup complete.")


__all__ = ["setup_app", "BinUpdater", "config", "DataUpdater", "DataReader"]
