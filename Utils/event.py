# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2023/3/7 0:35
# @Update  : 2024/3/15 10:21
# @Detail  : todo: 用不上暂时不处理

import os
import re
from collections import defaultdict
from typing import Union
from loguru import logger
import requests
from Data import DICT_PATH, EXTRAS_PATH
from Utils.common import dump_json, load_json, makedirs, re_replace, replace


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
    if name in os.listdir(EXTRAS_PATH):
        return load_keys(os.path.join(EXTRAS_PATH, name))


def check_extras_end(name):
    return check_extras(name, '_end')


class Event:

    def __init__(self, event_path: Union[str, os.PathLike], hashes_path: Union[str, os.PathLike]):
        """
        事件处理, 传入数据目录, 一般为 MANIFEST_PATH
        :param event_path: 事件目录
        :param hashes_path: 哈希表目录  Hashes E2A_HASH_PATH
        """
        self.hashes_path = hashes_path
        self.event_path = os.path.join(event_path, 'Events')

        self.repl_path = os.path.join(event_path, 'Repl')

        self._en_path = os.path.join(self.event_path, 'default')
        self._zh_path = os.path.join(self.event_path, 'zh_cn')

        makedirs(self._en_path)
        makedirs(self._zh_path)
        makedirs(self.repl_path)

        self._all_events = os.path.join(self.event_path, 'AllEvents.json')

        self._en_items_path = os.path.join(self._en_path, 'Items-en.json')
        self._zh_items_path = os.path.join(self._zh_path, 'Items-zh.json')

        self._zh_champions_path = os.path.join(self._zh_path, 'Champions-zh.json')

        # 最初输出的文件名
        self.repl_items_path = os.path.join(self.repl_path, 'Items.json')
        self.repl_champions_path = os.path.join(self.repl_path, 'Champions.json')
        self.repl_regions_path = os.path.join(self.repl_path, 'Regions.json')
        self.repl_skills_path = os.path.join(self.repl_path, 'Skills.json')
        self.repl_skills_end_path = os.path.join(self.repl_path, 'Skills_end.json')
        self.repl_skins_path = os.path.join(self.repl_path, 'Skins.json')
        self.repl_skins_end_path = os.path.join(self.repl_path, 'Skins_end.json')
        self.repl_skin_lines_path = os.path.join(self.repl_path, 'Skin_lines.json')
        self.repl_maps_path = os.path.join(self.repl_path, 'Maps.json')

        # 最终翻译文件
        self.kv = os.path.join(hashes_path, 'kv.json')

    def update_data(self):
        version = requests.get('https://ddragon.leagueoflegends.com/api/versions.json').json()[0]

        logger.debug(f'当前版本: {version}')
        champions_api = f'https://ddragon.leagueoflegends.com/cdn/{version}/data/zh_CN/champion.json'
        #
        champions_data = requests.get(champions_api).json()['data']
        champions = {int(item['key']): item for item in champions_data.values()}
        res = {}
        for item in game_data.get_summary():
            if item['id'] == -1:
                continue
            if item['id'] not in champions:
                logger.warning(f'ddragon中未找到 {item["name"]}-{item["alias"]} 对应的英雄, 可能为PBE新英雄')
                continue
            
            res.update({item['alias']: champions[item['id']]})

        dump_json(res, self._zh_champions_path)

        item_api = f'https://ddragon.leagueoflegends.com/cdn/{version}/data/zh_CN/item.json'
        dump_json(requests.get(item_api).json()['data'], self._zh_items_path)
        item_api = f'https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/item.json'
        dump_json(requests.get(item_api).json()['data'], self._en_items_path)

        for name, _ in champions_data.items():
            url = f'https://ddragon.leagueoflegends.com/cdn/{version}/data/zh_CN/champion/{name}.json'
            logger.debug(f'下载 {name} 数据')
            temp = requests.get(url).json()['data']
            res = temp[list(temp.keys())[0]]
            dump_json(res,  os.path.join(self._zh_path, f'{name.lower()}.json'))
            # download_file(url, os.path.join(self._zh_path, f'{name.lower()}.json'))

    def organize(self):
        """
        整理数据
        :return:
        """

        # 处理 英雄名字
        logger.debug('处理英雄名字')
        dump_json(game_data.get_champions_name(), self.repl_champions_path)

        self._get_skill()
        self._get_items()

        # 处理 联盟宇宙相关
        logger.debug('处理联盟宇宙相关')
        self._get_universe()

        # 处理 皮肤
        champions = load_json(self._zh_champions_path)
        logger.debug('处理皮肤')
        skins = defaultdict(dict)
        res = {}
        res_end = {}
        for name, items in champions.items():

            data = {
                'en_us': game_data_default.get_champion_detail_by_id(items['key'])["skins"],
                'zh_cn': game_data.get_champion_detail_by_id(items['key'])["skins"]}
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
        logger.debug('处理系列皮肤')
        zh_cn = game_data.get_skinlines()
        en_us = game_data_default.get_skinlines()
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
        logger.debug('处理地图信息')
        data = game_data.get_maps()
        dump_json({f'Map{str(item["id"])}': item['name'] for item in data}, self.repl_maps_path)

        logger.debug('生成替换字典完成')

    def _get_universe(self):
        """
        从联盟宇宙网站获取关键词信息
        :return:
        """
        region_api = 'https://yz.lol.qq.com/v1/zh_cn/faction-browse/index.json'
        region_data = requests.get(region_api).json()['factions']
        res = {item['slug'].replace('-', ''): item['name'] for item in region_data}

        other_api = 'https://yz.lol.qq.com/v1/dictionaries/zh_cn.json'
        other_data = requests.get(other_api).json()
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
        for data in game_data.get_summary():
            cid = data['id']
            name = data['alias']

            if cid == -1:
                continue

            res[name] = {}
            res_end[name] = {}
            sl = 'QWER'

            en_us = game_data_default.get_champion_detail_by_id(cid)
            zh_cn = game_data.get_champion_detail_by_id(cid)

            # PBE新英雄
            if name in champions:
                data = load_json(os.path.join(self._zh_path, f'{name.lower()}.json'))
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
        root = [os.path.join(self.hashes_path, 'zh_CN', 'VO', 'characters'),
                os.path.join(self.hashes_path, 'zh_CN', 'VO', 'maps')]
        res = {}
        for path in root:
            skins = {}
            items = os.listdir(path)
            for name in items:
                skins.update({
                    name: [os.path.join(path, name, i) for i in os.listdir(os.path.join(path, name))]
                })

            for name, skin in skins.items():
                event = []
                for item in skin:
                    values = load_json(item)['data'].values()
                    for v in values:
                        event.extend(list(v.keys()))
                    # event.extend(list(load_json(item)['data'].values())[0].keys())
                res[name] = event

        dump_json(res, self._all_events)

    # 翻译事件名
    def translate_event(self):
        """
        翻译事件名
        :return:
        """
        # champions = load_json(self.repl_champions_path)
        champions = game_data.get_champions_name()
        skill = load_json(self.repl_skills_path)
        skill_end = load_json(self.repl_skills_end_path)
        items = load_json(self.repl_items_path)
        skins = load_json(self.repl_skins_path)
        skin_end = load_json(self.repl_skins_end_path)
        skinlines = load_json(self.repl_skin_lines_path)
        regions = load_json(self.repl_regions_path)
        maps = load_json(self.repl_maps_path)
        events = load_json(self._all_events)

        fix = load_keys(os.path.join(DICT_PATH, 'words_fix.txt'))
        start = load_keys(os.path.join(DICT_PATH, 'start_cn.txt'))
        end = load_keys(os.path.join(DICT_PATH, 'end_cn.txt'))
        uin = load_keys(os.path.join(DICT_PATH, 'universe.txt'))
        map_del = load_keys(os.path.join(DICT_PATH, 'maps.txt'))
        item_del = load_keys(os.path.join(DICT_PATH, 'item_cn.txt'), '(已删除)')

        result = load_json(self.kv)
        for name, title in champions.items():
            if name == 'none':
                continue
            key = name
            result[key] = {}
            # if name != 'Kayle':
            #     continue
            logger.debug(f'处理{name}')
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
