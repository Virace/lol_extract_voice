# -*- coding: utf-8 -*-
# @Time    : 2021/2/25 0:41
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: PyCharm
# @Detail  : WAD操作(解包)

import os

from cdragontoolbox.wad import Wad
from cdragontoolbox.hashes import default_hashfile


def wad_extract(filename, output=None):
    """
    WAD文件解包
    :param filename: 输入文件名
    :param output: 输出目录名
    :return:
    """
    if not output:
        output = os.path.splitext(filename)[0]
    if not os.path.exists(output):
        os.mkdir(output)
    hashfile = default_hashfile(filename)
    wad = Wad(filename, hashes=hashfile.load())
    wad.guess_extensions()
    wad.extract(output, overwrite=True)
