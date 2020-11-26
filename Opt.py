#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2020/11/25 1:33
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : https://x-item.com
# @File    : Opt.py
# @Update  : 2020/11/25 1:33
# @Software: PyCharm
# @Detail  : 针对文件名进行优化


import os
import Config as config

OUT_PATH = os.path.join(config.OUT_PATH, 'Res')

for file_name in os.listdir(OUT_PATH):

    if '·' in file_name:
        champion = file_name.split('·')[0]
    else:
        champion = file_name

    for item in config.CHAMPION_INFO:
        if item['alias'].lower() == champion.lower():
            chinese = item['name']
            _id = item['id']
            champion_info = config.champion_info_by_id(_id)

            # 拼接文件名
            full_name = f'{champion_info["alias"]}·{champion_info["name"]}·{champion_info["title"]}'

            for skin in os.listdir(os.path.join(OUT_PATH, file_name)):

                # 为防止意外错误, 对已改名的进行排除
                if '·' in skin:
                    continue

                skin_cn = 'Base·基础'
                if skin != 'base':
                    for _item in champion_info['skins']:
                        if skin in _item['loadScreenPath'].lower():
                            # 实测中发现皮肤名字有Windows无法使用的字符, 替换之
                            skin_cn = '{}·{}'.format(skin.capitalize(), _item['name'].replace('/', '').replace(':', ''))
                        else:
                            # 下面判断炫彩? 只有星籁歌姬·萨勒芬妮这个英雄有这个问题
                            if 'questSkinInfo' in _item and 'tiers' in _item['questSkinInfo']:
                                for color_skin in _item['questSkinInfo']['tiers']:
                                    if skin in color_skin['loadScreenPath'].lower():
                                        skin_cn = '{}·{}'.format(skin.capitalize(),
                                                                 color_skin['name'].replace('/', '').replace(':', ''))

                    # 如果皮肤名字没有找到(中文翻译未更新), 那么就保持原样
                    if skin[0] in 'sb' and skin_cn == '基础':
                        skin_cn = skin

                # 更改皮肤文件夹名
                os.rename(os.path.join(OUT_PATH, file_name, skin), os.path.join(OUT_PATH, file_name, skin_cn))

            # 更改英雄文件夹名字
            os.rename(os.path.join(OUT_PATH, file_name), os.path.join(OUT_PATH, full_name))
