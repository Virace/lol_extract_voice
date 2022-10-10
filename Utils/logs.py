# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2022/8/27 12:07
# @Update  : 2022/9/23 15:35
# @Detail  : 描述

import os
import traceback
from concurrent.futures import as_completed

from loguru import logger

from config import GAME_REGION, LOG_PATH


def log_result(fs, func_name):
    """
    对异步函数的结果进行日志记录
    :param fs: 迭代对象
    :param func_name: 函数名
    :return:
    """
    _log_file = os.path.join(LOG_PATH, f'{func_name}.{GAME_REGION}.log')
    error_list = []
    for f in as_completed(fs):
        try:
            f.result()
        except Exception as exc:
            error_list.append((fs[f], exc))
            logger.warning(f'{func_name}, 遇到错误: {exc}, {fs[f]}')
            traceback.print_exc()

        else:
            logger.debug(f'{func_name}, 完成: {fs[f]}')

    if error_list:
        logger.error(f'{func_name}, 以下文件遇到错误: {error_list}')

    with open(_log_file, 'a+', encoding='utf-8') as f:
        for item in error_list:
            f.write(f'{item}\n')
