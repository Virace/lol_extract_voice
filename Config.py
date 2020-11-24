#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2020/11/24 19:31
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : https://x-item.com
# @File    : Config.py
# @Update  : 2020/11/24 19:31
# @Software: PyCharm

import os
import json


base = os.path.dirname(__file__)


# 游戏目录
GAME_PATH = r'D:\Games\Ol\Tencent\League of Legends'

# 输出目录
OUT_PATH = r'E:\Caches\Office\Temp'

# RExtractorConsole CLI
REC_CLI = os.path.join(base, 'tools', 'RavioliGameTools', 'RExtractorConsole.exe')

# 解包哪个国家, 需要什么填写什么.
# 如果留空则选取所有WAD文件, 小写
REGION = 'zh_cn'

# 最终文件夹是否用中文英雄名保存
CHINESE = True

# 读取英雄中文信息, 涉及到中文内容文件. 注意编码
CHAMPION_INFO = json.load(open(os.path.join(base, 'data', 'champion-summary.json'), encoding='utf-8'))
