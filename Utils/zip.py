# -*- coding: utf-8 -*-
# @Time    : 2021/2/25 0:52
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: PyCharm
# @Detail  : ZIP操作(解压)

import zipfile
from Utils.wrapper import check_time


@check_time
def extract(file, folder):
    zip_file = zipfile.ZipFile(file)
    return zip_file.extractall(folder)
