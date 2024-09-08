# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2022/8/26 14:00
# @Update  : 2024/9/3 10:42
# @Detail  : config.py

import json
import os

from dotenv import load_dotenv
from typing import Dict
from pathlib import Path

from lol_audio_unpack.Utils.type_hints import StrPath


ROOT_PATH = Path(__file__).resolve().parent.parent


class Config:
    _instance = None

    # 增加前缀防止冲突
    env_prefix: str = "LOL_"

    # 配置路径，默认为当前目录下的 .lol.env 文件
    env_path: StrPath = os.getenv("LOL_ENV_PATH", ROOT_PATH)

    # 是否只加载环境变量，True则不加载配置文件，默认为False
    env_only = bool(os.getenv("LOL_ENV_ONLY", False))

    def __new__(cls):
        if not cls._instance:
            cls._instance = super(Config, cls).__new__(cls)
            cls._load_and_set_env(cls._instance)

        return cls._instance

    @classmethod
    def _get_env(cls, key, metadata: Dict):
        """
        获取环境变量
        :param key:
        :param metadata:
        :return:
        """

        type_func = {
            "str": lambda x: x,
            "path": lambda x: Path(x) if x else "",
            "list": lambda x: x.split(",") if x else [],
        }

        required = metadata.get("required", False)
        default = metadata.get("default", None)
        _type = metadata.get("type", "str")

        data = type_func[_type](os.getenv(f"{cls.env_prefix}{key}", default))

        if required and not data:
            raise ValueError(f"{cls.env_prefix}{key}不能为空")

        return data

    @classmethod
    def _load_and_set_env(cls, instance):
        """
        加载环境变量并设置实例属性
        :param instance: 实例
        :return:
        """

        if not cls.env_only:
            load_dotenv(dotenv_path=cls.env_path, override=True)
        cls.params = json.loads((ROOT_PATH / "params.json").read_text())
        for param, metadata in cls.params.items():
            data = cls._get_env(param, metadata)

            # 属性赋值时去掉前缀
            setattr(instance, param.replace(cls.env_prefix, ""), data)

        out_path = getattr(instance, "OUTPUT_PATH")
        game_path = getattr(instance, "GAME_PATH")

        # 音频目录, 最终解包生成的音频文件都放在这
        setattr(instance, "AUDIO_PATH", out_path / "audios")

        # 缓存目录, 解包生成的一些文件会放在这里, 可以删除
        setattr(instance, "TEMP_PATH", out_path / "temps")

        # 日志目录, 一些文件解析错误不会关闭程序而是记录在日志中
        setattr(instance, "LOG_PATH", out_path / "logs")

        # 哈希目录, 存放所有与 k,v 相关数据
        setattr(instance, "HASH_PATH", out_path / "hashes")

        # 有关于游戏内的数据文件
        setattr(instance, "MANIFEST_PATH", out_path / "manifest")

        # 游戏版本文件, 用来记录当前解包文件的版本
        setattr(instance, "LOCAL_VERSION_FILE", out_path / "game_version")

        # 游戏英雄文件目录 (Game/DATA/FINAL/Champions)
        setattr(
            instance,
            "GAME_CHAMPION_PATH",
            game_path / "Game" / "DATA" / "FINAL" / "Champions",
        )

        # 游戏地图(公共)文件目录 (Game/DATA/FINAL/Maps/Shipping)
        setattr(
            instance,
            "GAME_MAPS_PATH",
            game_path / "Game" / "DATA" / "FINAL" / "Maps" / "Shipping",
        )

        # 游戏大厅资源目录
        setattr(
            instance,
            "GAME_LCU_PATH",
            game_path / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data",
        )

        # 修正
        if getattr(instance, "GAME_REGION").lower() == "en_us":
            setattr(instance, "GAME_REGION", "default")

    def reload_config(self):
        """
        重新加载配置
        :return:
        """
        self._load_and_set_env(self)


config_instance = Config()
