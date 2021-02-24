# -*- coding: utf-8 -*-
# @Time    : 2021/2/25 0:45
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: PyCharm
# @Detail  : RavioliGameTools操作

import os
import subprocess
import Ravioli
from Utils import downloader, wrapper, zip


def voice_extract(filename, output):
    """
    语音类文件解包(不准确)
    :param filename: 输入文件名
    :param output: 输出目录名
    :return:
    """
    # 如果不想看到输出, 可以使用其他方式调用
    cp = subprocess.run(
        [
            '',
            filename,
            output,
            '/soundformat:wav'
        ],
        stdout=subprocess.DEVNULL,
        timeout=999999999
    )
    return cp.returncode


@wrapper.check_time
def update_tools():
    """
    更新RavioliGameTools, 如果报错请修改链接
    :return:
    """
    url_list = [
        # 'http://www.scampers.org/steve/sms/other/RavioliGameTools_v2.10.zip',
        # 'http://www.scampers.org/steve/sms/other/RavioliGameTools_v2.10_Patch1.zip'
        'https://cdn.jsdelivr.net/gh/Virace/jsDelivr-CDN/other/tools/RavioliGameTools_v2.10.zip',
        'https://cdn.jsdelivr.net/gh/Virace/jsDelivr-CDN/other/tools/RavioliGameTools_v2.10_Patch1.zip',
    ]
    save_path = Ravioli.RGT_CWD
    for item in url_list:
        this_file = os.path.join(save_path, os.path.basename(item))
        downloader.get(item, this_file)
        zip.extract(this_file, save_path)
        os.unlink(this_file)
