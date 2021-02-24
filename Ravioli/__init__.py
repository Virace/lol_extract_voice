# -*- coding: utf-8 -*-
# @Time    : 2021/2/25 0:51
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: PyCharm
# @Detail  :

import os

RGT_CWD = os.path.join(os.path.dirname(__file__), 'bin')
RGT_CLI = os.path.join(RGT_CWD, 'RExtractorConsole.exe')

__all__ = [RGT_CWD, RGT_CLI]