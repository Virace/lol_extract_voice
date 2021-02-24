# -*- coding: utf-8 -*-
# @Time    : 2021/2/25 0:32
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: PyCharm
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
        log.debug(f'Func: {func.__module__}.{func.__name__}, Time Spent: {round(time.time() - st, 2)}')
        return ret

    return wrapper
