# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2022/8/15 23:56
# @Update  : 2022/10/10 21:20
# @Detail  : 描述

import json
import os
import traceback
from pathlib import Path

from loguru import logger
from lol_voice.formats import WAD

from Utils.common import format_region
from config import GAME_PATH, GAME_REGION, MANIFEST_PATH


class GameData:
    """
    获取本地游戏相关数据
    """

    def __init__(self):
        self.game_path = Path(GAME_PATH)
        self.out_path = Path(MANIFEST_PATH)
        self.region = GAME_REGION
        self.data_path = self.game_path / 'LeagueClient' / 'Plugins' / 'rcp-be-lol-game-data'
        self.wad_file_region = self.data_path / f'{format_region(self.region)}-assets.wad'
        self.wad_file_default = self.data_path / 'default-assets.wad'

    def _get_out_path(self, before: [str, list[str]] = ''):
        if isinstance(before, str):
            before = [before]
        return (self.out_path / self.region).joinpath(*before)

    def _open_file(self, filename):
        file = self._get_out_path(filename)
        if not os.path.exists(file):
            logger.warning(f'{file}不存在')
            return {}
        try:
            with open(file, encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            e = traceback.format_exc()
            logger.warning(e)
            return {}

    def get_summary(self, ):
        return self._open_file('champion-summary.json')

    def get_skins(self, ):
        return self._open_file('skins.json')

    def get_skinlines(self, ):
        temp = self._open_file('skinlines.json')
        result = {item['id']: item['name'] for item in temp}
        return result

    def get_maps(self, ):
        return self._open_file('maps.json')

    def get_champion_detail_by_id(self, cid, ):
        return self._open_file(['champions', f'{cid}.json'])

    def get_champion_name(self, name, chinese=True):
        """
        根据游戏数据获取中文名称
        :param name:
        :param chinese:
        :return:
        """
        summary = self.get_summary()
        for item in summary:
            if item['alias'].lower() == name.lower():
                if chinese:
                    return item['alias'], item['name']
                else:
                    return item['alias']

    def get_champions_name(self, ):
        return {item['alias'].lower(): item['name'] for item in self.get_summary()}

    def get_champions_id(self, ):
        return [item['id'] for item in self.get_summary()]

    def get_maps_id(self, ):
        return [item['id'] for item in self.get_maps()]

    def get_manifest(self):
        """
        获取文件清单
        :return:
        """
        logger.trace('获取文件清单')
        if self.region == 'en_us':
            region = 'default'

        def output_file_name(path):
            old = f'plugins/rcp-be-lol-game-data/global/{region}/v1/'
            new = path.replace(old, '')
            return os.path.join(self._get_out_path(), os.path.normpath(new))

        hash_table = [
            f'plugins/rcp-be-lol-game-data/global/{self.region}/v1/champion-summary.json',
            f'plugins/rcp-be-lol-game-data/global/{self.region}/v1/skinlines.json',
            f'plugins/rcp-be-lol-game-data/global/{self.region}/v1/skins.json',
            f'plugins/rcp-be-lol-game-data/global/{self.region}/v1/maps.json',
            f'plugins/rcp-be-lol-game-data/global/{self.region}/v1/universes.json'
        ]
        WAD(self.wad_file_region).extract(hash_table, out_dir=output_file_name)
        WAD(self.wad_file_region).extract(
            [f'plugins/rcp-be-lol-game-data/global/{self.region}/v1/champions/{item["id"]}.json' for item in
             self.get_summary()],
            out_dir=output_file_name)

    def get_images(self):
        """
        获取英雄有关图片文件(头像、原画等)
        :return:
        """
        _hash_list = []
        _head = f'plugins/rcp-be-lol-game-data/global/default'

        def fix_hash_path(path):
            return f"{_head}/{path.replace('/lol-game-data/assets/', '')}"

        def output_file_name(path):
            old = 'plugins/rcp-be-lol-game-data/global/default/v1/'
            loading = f'plugins/rcp-be-lol-game-data/global/default/ASSETS/Characters'
            new = path.replace(old, '')
            new = new.replace(loading, 'champion-loadscreen')

            return os.path.join(self.out_path, 'images', os.path.normpath(new))

        champions = self.get_summary()
        for champion in champions:
            cid = champion['id']

            c_data = self.get_champion_detail_by_id(cid)
            _hash_list.append(fix_hash_path(c_data['squarePortraitPath']))

            for item in c_data['skins']:
                # "splashPath": "/lol-game-data/assets/v1/champion-splashes/2/2000.jpg",
                # "uncenteredSplashPath": "/lol-game-data/assets/v1/champion-splashes/uncentered/2/2000.jpg",
                # "tilePath": "/lol-game-data/assets/v1/champion-tiles/2/2000.jpg",
                # "loadScreenPath": "/lol-game-data/assets/ASSETS/Characters/Olaf/Skins/Base/OlafLoadScreen.jpg",

                _hash_list.append(f'{_head}/v1/champion-splashes/{cid}/{item["id"]}.jpg')
                _hash_list.append(f'{_head}/v1/champion-splashes/uncentered/{cid}/{item["id"]}.jpg')
                _hash_list.append(f'{_head}/v1/champion-tiles/{cid}/{item["id"]}.jpg')
                _hash_list.append(fix_hash_path(item['loadScreenPath']))

                # 炫彩
                if 'chromas' in item:
                    _hash_list.append(f'{_head}/v1/chromaPath/{cid}/{item["id"]}.jpg')
                    for chroma in item['chromas']:
                        _hash_list.append(f'{_head}/v1/champion-chroma-images/{cid}/{item["id"]}/{chroma["id"]}.jpg')
        WAD(self.wad_file_default).extract(_hash_list, out_dir=output_file_name)

    def get_game_version(self, default='99.99'):
        meta = self.game_path / 'Game' / 'code-metadata.json'
        if os.path.exists(meta):
            with open(meta, encoding='utf-8') as f:
                data = json.load(f)
            version_v = data['version']
        else:
            return default
        return version_v.split('+')[0]

    def update_data(self):
        """
        根据本地游戏文件获取 数据文件
        :return:
        """
        _region = self.region
        # 游戏内英文文件作为default默认存在
        if self.region == 'en_us':
            _region = 'default'

        def output_file_name(path):
            old = f'plugins/rcp-be-lol-game-data/global/{_region}/v1/'
            new = path.replace(old, '')
            return os.path.join(MANIFEST_PATH, _region, os.path.normpath(new))

        data_path = os.path.join(self.game_path, 'LeagueClient', 'Plugins', 'rcp-be-lol-game-data')

        wad_file = os.path.join(data_path, f'{format_region(_region)}-assets.wad')
        hash_table = [
            f'plugins/rcp-be-lol-game-data/global/{_region}/v1/champion-summary.json',
            f'plugins/rcp-be-lol-game-data/global/{_region}/v1/skinlines.json',
            f'plugins/rcp-be-lol-game-data/global/{_region}/v1/skins.json',
            f'plugins/rcp-be-lol-game-data/global/{_region}/v1/maps.json',
            f'plugins/rcp-be-lol-game-data/global/{_region}/v1/universes.json'
        ]
        WAD(wad_file).extract(hash_table, out_dir=output_file_name)
        WAD(wad_file).extract(
            [f'plugins/rcp-be-lol-game-data/global/{_region}/v1/champions/{item["id"]}.json' for item in
             self.get_summary()],
            out_dir=output_file_name)
