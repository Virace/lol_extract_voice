# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2022/8/27 12:07
# @Update  : 2024/8/30 7:04
# @Detail  : 描述

import traceback
from concurrent.futures import as_completed
from pathlib import Path
from typing import Optional

from loguru import logger

from Utils.type_hints import StrPath


def log_result(fs, func_name, region: Optional[str] = "", log_path: StrPath = ""):
    """
    对异步函数的结果进行日志记录
    :param fs: 迭代对象
    :param func_name: 函数名
    :param region: 地区
    :param log_path: 日志路径
    :return:
    """
    _log_file = Path(log_path) / f"{func_name}.{region}.log"
    error_list = []
    for f in as_completed(fs):
        try:
            f.result()
            logger.debug(f"{func_name}, 完成: {fs[f]}")
        except Exception as exc:
            error_list.append((fs[f], exc))
            logger.warning(f"{func_name}, 遇到错误: {exc}, {fs[f]}")
            traceback.print_exc()

        else:
            logger.debug(f"{func_name}, 完成: {fs[f]}")

    if error_list:
        logger.error(f"{func_name}, 以下文件遇到错误: {error_list}")

    with _log_file.open("a+", encoding="utf-8") as f:
        for item in error_list:
            f.write(f"{item}\n")


def task_done_callback(future, task_info):
    """
    任务完成后的回调函数，用于处理异常并记录日志
    :param future: 执行的任务
    :param task_info: 任务的相关信息，用于日志记录
    """
    try:
        future.result()
        logger.info(f"任务完成: {task_info}")
    except Exception as exc:
        error_info = traceback.format_exc()
        logger.error(f"任务失败: {task_info}")
        logger.error(f"异常信息: {exc}")
        logger.error(f"追踪信息:\n{error_info}")