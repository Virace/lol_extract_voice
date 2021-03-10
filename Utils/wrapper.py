# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: PyCharm
# @Create  : 2021/2/25 0:32
# @Update  : 2021/3/5 23:6
# @Detail  : 

import time
import logging

log = logging.getLogger(__name__)


def check_time(func):
    """
    获取函数执行时间
    :param func:
    :return:
    """
    def wrapper(*args, **kwargs):
        st = time.time()
        ret = func(*args)
        log.info(f'Func: {func.__module__}.{func.__name__}, Time Spent: {round(time.time() - st, 2)}')
        return ret

    return wrapper
