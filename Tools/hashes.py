# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: PyCharm
# @Create  : 2021/2/24 23:41
# @Update  : 2021/3/4 22:20
# @Detail  : 哈希值更新

import os
import logging
import Hashes
from Utils import downloader, wrapper

log = logging.getLogger(__name__)

UPDATE_LIST = ['hashes.game.txt',
               'hashes.lcu.txt']


@wrapper.check_time
def update_hash():
    """
    更新本地包中哈希表.
    函数中使用的链接为代理链接, 如国外用户请直接注释中GitHub链接
    :return:
    """
    # https://raw.githubusercontent.com/CommunityDragon/CDTB/master/cdragontoolbox/
    # https://ghproxy.com/https://raw.githubusercontent.com/CommunityDragon/CDTB/master/cdragontoolbox/
    url = 'https://ghproxy.com/https://raw.githubusercontent.com/CommunityDragon/CDTB/master/cdragontoolbox/'
    save_path = os.path.dirname(Hashes.__file__)
    log.debug(f'Hashes Path: {save_path}')
    for item in UPDATE_LIST:
        log.info(f'Download file: {item}')
        downloader.get(f'{url}{item}', os.path.join(save_path, item))
