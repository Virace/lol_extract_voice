# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2023/3/7 0:35
# @Update  : 2024/8/22 0:38
# @Detail  : 

import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Callable

from loguru import logger

from Data import DICT_PATH, EXTRAS_PATH
from Data.Manifest import GameData
from Utils.common import dump_json, load_json, makedirs, re_replace, replace
from Utils.type_hints import StrPath
from common import fetch_json_data


def txt2dict(data, suffix=''):
    """
    将txt转换为字典
    :param data:
    :param suffix:
    :return:
    """
    res = {}
    for item in data.split('\n'):
        if item == '':
            continue
        temp = item.split()
        res.update({
            temp[0]: f'{temp[-1]}{suffix}'
        })
    return {item: res[item] for item in sorted(res, key=lambda x: len(x), reverse=True)}


def load_keys(file, suffix=''):
    """
    从txt文件中加载键值对
    :param file:
    :param suffix:
    :return:
    """
    with open(file, encoding='utf-8') as f:
        data = f.read()
        return txt2dict(data, suffix)


def check_extras(name, suffix=''):
    """
    检查额外的键值对
    :param name:
    :param suffix:
    :return:
    """
    name = f'{name.lower()}{suffix}.txt'
    if name in EXTRAS_PATH.iterdir():
        return load_keys(EXTRAS_PATH / name)


def check_extras_end(name):
    return check_extras(name, '_end')


class Event:

    def __init__(self, manifest_path: StrPath, hash_path: StrPath, game_path: StrPath, version: str = '99.99'):
        """
        事件处理, 传入数据目录
        :param manifest_path: 事件目录
        :param hash_path: 哈希表目录  Hashes E2A_HASH_PATH
        """

        self._ddragon_version_api = 'https://ddragon.leagueoflegends.com/api/versions.json'
        dd_version = fetch_json_data(self._ddragon_version_api)[0]

        self.hash_path = Path(hash_path) / version / 'event2audio'
        self.manifest_path = Path(manifest_path) / dd_version / 'Events'

        self.repl_path = Path(manifest_path) / dd_version / 'Repl'

        self._en_path = self.manifest_path / 'default'
        self._zh_path = self.manifest_path / 'zh_cn'

        self.game_data = GameData(game_path, manifest_path, 'zh_cn')
        self.game_data_default = GameData(game_path, manifest_path, "en_us")

        makedirs(self._en_path)
        makedirs(self._zh_path)
        makedirs(self.repl_path)

        self._all_events = self.manifest_path / 'AllEvents.json'

        self._en_items_path = self._en_path / 'Items-en.json'
        self._zh_items_path = self._zh_path / 'Items-zh.json'

        self._zh_champions_raw_path = self._zh_path / 'Champions-raw-zh.json'
        self._zh_champions_path = self._zh_path / 'Champions-zh.json'

        # 最初输出的文件名
        self.repl_items_path = self.repl_path / 'Items.json'
        self.repl_champions_path = self.repl_path / 'Champions.json'
        self.repl_regions_path = self.repl_path / 'Regions.json'
        self.repl_skills_path = self.repl_path / 'Skills.json'
        self.repl_skills_end_path = self.repl_path / 'Skills_end.json'
        self.repl_skins_path = self.repl_path / 'Skins.json'
        self.repl_skins_end_path = self.repl_path / 'Skins_end.json'
        self.repl_skin_lines_path = self.repl_path / 'Skin_lines.json'
        self.repl_maps_path = self.repl_path / 'Maps.json'

        logger.info(f'本地版本: {version}, ddragon版本: {dd_version}')
        self._ddragon_champions_cn_api = f'https://ddragon.leagueoflegends.com/cdn/{dd_version}/data/zh_CN/champion.json'
        self._ddragon_item_zh_api = f'https://ddragon.leagueoflegends.com/cdn/{dd_version}/data/zh_CN/item.json'
        self._ddragon_item_en_api = f'https://ddragon.leagueoflegends.com/cdn/{dd_version}/data/zh_CN/item.json'
        self._ddragon_champion_cn_api = f'https://ddragon.leagueoflegends.com/cdn/{dd_version}/data/zh_CN/champion/{{name}}.json'

        # 最终翻译文件
        self.kv = Path(manifest_path) / f'kv.{version}.json'

    @classmethod
    def _fetch_and_save(cls, url, path, force_update=False, _call: Callable = None, **kwargs):
        """
        从指定URL获取数据并保存到文件。 如果文件存在且大小大于空字典的大小，则不执行下载。
        如果force_update为True，则无论文件是否存在，都会重新获取数据并保存。

        :param url: 要获取数据的URL
        :param path: 保存文件的路径
        :param force_update: 是否强制更新文件，默认值为False
        :param kwargs: 传递给fetch_json_data的其他参数
        :return: None
        """
        path = Path(path)
        empty_dict_size = len(json.dumps({}))  # 空字典的大小

        if path.exists() and not force_update:
            if path.stat().st_size > empty_dict_size:
                logger.debug(f"{path} 文件已存在且大小符合要求，跳过下载")
                return

        logger.debug(f"正在从 {url} 获取数据并保存到 {path}")

        data = fetch_json_data(url, **kwargs)['data']
        if _call:
            data = _call(data)
        dump_json(data, path)

    def update_data(self):

        # 下载并保存RAW数据
        self._fetch_and_save(self._ddragon_champions_cn_api,
                             self._zh_champions_raw_path)
        champions_data = load_json(self._zh_champions_raw_path)
        champions = {int(item['key']): item for item in champions_data.values()}
        res = {}
        for item in self.game_data.get_summary():
            if item['id'] == -1:
                continue
            if item['id'] not in champions:
                logger.warning(f'ddragon中未找到 {item["name"]}-{item["alias"]} 对应的英雄, 可能为PBE新英雄')
                continue

            res.update({item['alias']: champions[item['id']]})

        dump_json(res, self._zh_champions_path)

        self._fetch_and_save(self._ddragon_item_zh_api, self._zh_items_path)
        self._fetch_and_save(self._ddragon_item_en_api, self._en_items_path)

        for name, _ in champions_data.items():
            logger.info(f'下载 {name} 数据')
            self._fetch_and_save(self._ddragon_champion_cn_api.format(name=name),
                                 self._zh_path / f'{name.lower()}.json',
                                 _call=lambda x: list(x.values())[0])

    def organize(self):
        """
        整理数据
        :return:
        """

        # 处理 英雄名字
        logger.info('处理英雄名字')
        dump_json(self.game_data.get_champions_name(), self.repl_champions_path)

        self._get_skill()
        self._get_items()

        # 处理 联盟宇宙相关
        logger.info('处理联盟宇宙相关')
        self._get_universe()

        # 处理 皮肤
        champions = load_json(self._zh_champions_path)
        logger.info('处理皮肤')
        skins = defaultdict(dict)
        res = {}
        res_end = {}
        for name, items in champions.items():

            data = {
                'en_us': self.game_data_default.get_champion_detail_by_id(items['key'])["skins"],
                'zh_cn': self.game_data.get_champion_detail_by_id(items['key'])["skins"]}
            for region, data in data.items():
                for item in data:
                    if not item['isBase']:
                        skin_id = str(item['id']).replace(items['key'], '', 1).lstrip('0')
                        skins[item['id']].update({region: item['name'], 'name': name, 'key': skin_id})
                        # skins.update({_id: (item['name'], name)})

                    if 'chromas' in item and region == 'zh_cn':
                        for ch in item['chromas']:
                            skin_id = str(ch["id"]).replace(items['key'], '', 1).lstrip('0')
                            skins[ch["id"]].update({region: ch['name'], 'name': name, 'key': skin_id})
                            # skins.update({ch["id"]: (ch['name'], name)})
        for _id, items in skins.items():
            sid = items['key']
            res_end.update({f'{items["name"]}Skin{sid}': items["zh_cn"]})
            res.update({f'{items["name"]}Skin{sid.zfill(2)}': items["zh_cn"]})
            if 'en_us' in items:
                temp = re.compile(r"[' ]").sub('', items["en_us"])
                res.update({f'{temp}': items["zh_cn"]})
        dump_json(res, self.repl_skins_path)
        dump_json(res_end, self.repl_skins_end_path)

        # 处理 系列皮肤
        logger.info('处理系列皮肤')
        zh_cn = self.game_data.get_skinlines()
        en_us = self.game_data_default.get_skinlines()
        data = {sid: {'zh_cn': name} for sid, name in zh_cn.items()}
        for sid, name in en_us.items():
            data[sid].update({'en_us': name})
        res = {item['en_us'].replace(' ', '').replace('-', ''): f"{item['zh_cn']}系列皮肤"
               for item in data.values() if item['zh_cn'] != ''}
        for item in data.values():
            if item['zh_cn'] != '':
                key = item['en_us'].replace(' ', '').replace('-', '')
                res.update({key: f"{item['zh_cn']}系列皮肤"})
                if ':' in key:
                    res.update({key.split(':')[-1]: f"{item['zh_cn']}系列皮肤"})
        dump_json(res, self.repl_skin_lines_path)

        # 处理 地图信息
        logger.info('处理地图信息')
        data = self.game_data.get_maps()
        dump_json({f'Map{str(item["id"])}': item['name'] for item in data}, self.repl_maps_path)

        logger.info('生成替换字典完成')

    def _get_universe(self):
        """
        从联盟宇宙网站获取关键词信息
        :return:
        """
        region_api = 'https://yz.lol.qq.com/v1/zh_cn/faction-browse/index.json'
        region_data = fetch_json_data(region_api)['factions']
        res = {item['slug'].replace('-', ''): item['name'] for item in region_data}

        other_api = 'https://yz.lol.qq.com/v1/dictionaries/zh_cn.json'
        other_data = fetch_json_data(other_api)
        for key, value in other_data.items():
            gourp = re.compile(r'^(race|role|faction)-(.*)').findall(key)
            if gourp and value is not None:
                res.update({gourp[-1][-1].replace('-', ''): value})
        dump_json(res, self.repl_regions_path)

    def _get_items(self):
        """
        获取装备字典
        :return:
        """
        # 处理 装备相关
        logger.debug('处理装备相关')

        en_items = load_json(self._en_items_path)
        cn_items = load_json(self._zh_items_path)

        res_items = {}
        items = {}
        for key, value in en_items.items():
            items.update({key: {'en': value['name']}})
        for key, value in cn_items.items():
            items[key].update({'cn': value['name']})

        for key, value in items.items():
            res_items.update({key: value['cn']})

            res_items.update({re.compile("[ -.']").sub('', value['en']): value['cn']})

        dump_json(res_items, self.repl_items_path)

    def _get_skill(self):
        """
        获取英雄技能字典
        :return:
        """
        # 处理英雄技能, 必须从ddragon.leagueoflegends.com 获取英雄数据
        logger.debug('处理英雄技能')
        champions = load_json(self._zh_champions_path)
        res = dict()
        res_end = dict()
        for data in self.game_data.get_summary():
            cid = data['id']
            name = data['alias']

            if cid == -1:
                continue

            res[name] = {}
            res_end[name] = {}
            sl = 'QWER'

            en_us = self.game_data_default.get_champion_detail_by_id(cid)
            zh_cn = self.game_data.get_champion_detail_by_id(cid)

            # PBE新英雄
            if name in champions:
                data = load_json(self._zh_path / f'{name.lower()}.json')
                res[name].update({'Passive': f'{data["passive"]["name"]}(被动技能)'})
                res_end[name].update({f'{name}P': f'{data["passive"]["name"]}(被动技能)', })

                for item in data['spells']:
                    index = data['spells'].index(item)
                    res[name].update({item['id']: f"{item['name']}({sl[index]}技能)"})

            res[name].update({
                en_us['passive']['name'].replace('!', '').replace(' ', '').replace('-', '')
                : f"{zh_cn['passive']['name']}(被动技能)"})
            en = {item['spellKey']: item['name'] for item in en_us['spells']}
            cn = {item['spellKey']: item['name'] for item in zh_cn['spells']}
            for key, value in en.items():
                res[name].update({
                    value.replace('!', '').replace(' ', '').replace('-', ''): f'{cn[key]}({key.upper()}技能)'
                })
                res[name].update({
                    f'{name}{key.upper()}': f'{cn[key]}({key.upper()}技能)'
                })

        dump_json(res, self.repl_skills_path)
        dump_json(res_end, self.repl_skills_end_path)

    def collect_event(self):
        """
        收集所有事件名
        :return:
        """
        root = [self.hash_path / 'zh_CN' / 'VO' / 'characters',
                self.hash_path / 'zh_CN' / 'VO' / 'maps']
        res = {}
        for path in root:
            skins = {}
            for name_path in path.iterdir():
                skins.update({
                    # 英雄名: [skin文件列表]
                    name_path.name: [str(i) for i in name_path.iterdir()]
                })

            for name, skin in skins.items():
                _event = []
                for item in skin:
                    values = load_json(item)['data'].values()
                    for v in values:
                        _event.extend(list(v.keys()))
                    # event.extend(list(load_json(item)['data'].values())[0].keys())
                res[name] = _event

        dump_json(res, self._all_events)

    # 翻译事件名
    def translate_event(self):
        """
        翻译事件名
        :return:
        """
        # champions = load_json(self.repl_champions_path)
        champions = self.game_data.get_champions_name()
        skill = load_json(self.repl_skills_path)
        skill_end = load_json(self.repl_skills_end_path)
        items = load_json(self.repl_items_path)
        skins = load_json(self.repl_skins_path)
        skin_end = load_json(self.repl_skins_end_path)
        skinlines = load_json(self.repl_skin_lines_path)
        regions = load_json(self.repl_regions_path)
        maps = load_json(self.repl_maps_path)
        events = load_json(self._all_events)

        fix = load_keys(DICT_PATH / 'words_fix.txt')
        start = load_keys(DICT_PATH / 'start_cn.txt')
        end = load_keys(DICT_PATH / 'end_cn.txt')
        uin = load_keys(DICT_PATH / 'universe.txt')
        map_del = load_keys(DICT_PATH / 'maps.txt')
        item_del = load_keys(DICT_PATH / 'item_cn.txt', '(已删除)')

        result = load_json(self.kv)
        for name, title in champions.items():
            if name == 'none':
                continue
            key = name
            result[key] = {}
            # if name != 'Kayle':
            #     continue
            logger.info(f'处理{name}')
            skill_this = skill[name]
            skill_this_end = skill_end[name]
            # name = name.capitalize()

            data = ''
            # data = '\n'.join(events[name])
            # 处理后缀
            for item in events[name]:
                group = re.compile('(3D|2D)').search(item)
                if group:
                    tt = group.group(0)
                    temp = f'{item.replace(tt, "")} - {tt}音效\n'
                else:
                    temp = f'{item}\n'
                data += temp
            # 去掉最后的换行
            data = data[:-1]

            text = events[name]

            # 修复错误
            data = re_replace(data, fix)

            if extra := check_extras(name):
                data = re_replace(data, extra)

            data = re_replace(data, skill_this)

            # 通用替换
            data = replace(data, start)
            if name == 'drmundo':
                name = '(Mundo|DrMundo)'
            data = re.compile(rf'Play_vo_{name}(Skin\d+|Classic)?_?({name}|Base)?', re.I).sub('', data)
            # data = re.compile(rf'Play_vo_(\w+)?{name}(Skin\d+|Classic)?_?({name}|Base)?', re.I).sub('', data)

            data = re_replace(data, uin)
            # 替换皮肤
            data = re_replace(data, skins)
            data = re_replace(data, skin_end)

            data = re_replace(data, skinlines)

            if extra := check_extras_end(name):
                data = re_replace(data, extra)

            # 替换英雄
            champions = {item: champions[item] for item in sorted(champions, key=lambda x: len(x), reverse=True)}
            data = re_replace(data, champions)
            # 替换物品
            data = replace(data, items)

            data = replace(data, item_del)

            data = re_replace(data, maps)
            data = re_replace(data, map_del)
            data = re_replace(data, regions)

            # data = replace(data, skill_this_end)
            data = replace(data, end)

            data = re_replace(data, {
                r'Skin\d+': '',
                'Play_(vo_)?': ''
            })

            lines = data.split('\n')

            res = ''
            for i in range(len(lines)):
                # print(line)
                # '_'.join(line.split('_')[3:])
                # group = re.compile(r'[a-zA-Z]{2,}').search(lines[i])
                # group = re.compile(r'\d{4}').search(lines[i])
                # if group and group.group() not in ['buff', 'Buff', 'BUFF', 'VO', 'SFX', 'EQ', 'AOE', 'DJ', 'KDA', 'BOSS']:
                #     print('{}  {}   {}\n'.format(key, text[i], lines[i]))
                # res += f'{text[i]}, {lines[i]}\n'
                # print('{}   {}'.format(text[i], lines[i]))
                result[key][text[i]] = lines[i]

            # if res:
            #     print(title)
            #     print(res)
            # print(data)
        dump_json(result, self.kv)
        logger.success(f'kv file: {self.kv}')


if __name__ == '__main__':
    import sys

    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from config import config_instance

    logger.configure(handlers=[
        dict(sink=sys.stdout, level="INFO")
    ])

    event = Event(
        game_path=config_instance.GAME_PATH,
        hash_path=config_instance.HASH_PATH,
        manifest_path=config_instance.MANIFEST_PATH,
        version='14.11'
    )
    # 从dd更新数据
    event.update_data()
    # 收集所有事件名
    event.collect_event()

    event.organize()
    event.translate_event()
