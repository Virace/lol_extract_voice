#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2020/11/24 22:58
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : https://x-item.com
# @File    : Guess.py
# @Update  : 2020/11/24 22:58
# @Software: PyCharm
# @Detail  : 试听文件

import os
import json

import Config as config

import winsound

OUT_PATH = os.path.join(r'D:\lol', 'Res')


ignore = ['Bard']

for root, dirs, files in os.walk(OUT_PATH):
    if files:
        for item in files:
            if '·' in item or 'Base' not in root:
                continue

            if os.path.basename(os.path.dirname(root)).split('·')[0] in ignore:
                continue

            this = os.path.join(root, item)
            this_id = os.path.basename(this).split('.')[0]
            print(this)

            while True:
                winsound.PlaySound(this, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP)
                i = input('请输入:')
                if i == '':
                    continue
                elif i.upper() == 'Q':
                    exit()
                elif i == ' ':
                    break
                else:
                    os.rename(this, os.path.join(root, f'{this_id}·{i}.wav'))
                    break
