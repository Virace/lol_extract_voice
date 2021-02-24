# -*- coding: utf-8 -*-
# @Time    : 2021/2/25 0:14
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: PyCharm
# @Detail  : 下载器

import logging
import requests
from Utils.wrapper import check_time

log = logging.getLogger(__name__)


@check_time
def get(url: str, file: str, chunk_size: int = 10240):
    """
    get方式下载文件
    :param url: 网络地址
    :param file: 本地路径
    :param chunk_size: 块大小
    :return:
    """
    resp = requests.get(url, stream=True)
    resp.raise_for_status()
    with open(file, 'wb') as f:
        for chunk in resp.iter_content(chunk_size):
            f.write(chunk)
