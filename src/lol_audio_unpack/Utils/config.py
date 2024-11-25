# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2022/8/26 14:00
# @Update  : 2024/11/25 21:52
# @Detail  : config.py

import json
import os
import sys
from pathlib import Path
from typing import Dict, Any

from dotenv import load_dotenv
from loguru import logger

from lol_audio_unpack.Utils.type_hints import StrPath

ROOT_PATH = Path(__file__).resolve().parent.parent


class Config:
    _instance = None  # 单例实例

    def __new__(cls, *args, **kwargs):
        # 暂时设置成单例模式，目前没有多实例的用途
        if not cls._instance:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, env_path: StrPath = None, env_prefix: StrPath = None, **kwargs):
        """
        初始化配置管理模块。
        :param env_path: 配置文件路径
        :param env_prefix: 配置文件项前缀
        :param kwargs: 传入的参数 (优先级最高)
        """
        if self._initialized:
            return
        self._initialized = True

        # 初始化基础配置
        self.env_path = env_path  # 环境变量文件路径
        self.env_prefix = env_prefix if env_prefix else "LOL_"  # 环境变量前缀
        self.params = self._load_params()
        self.settings = {}  # 保存最终参数值
        self.debug_source = {}  # 保存参数来源

        # 加载 .env 文件（如果提供了 env_path）
        if self.env_path:
            self._load_from_file()

        # 处理传入的 kwargs 参数（最高优先级）
        self._load_from_kwargs(kwargs)

        # 加载环境变量和默认值
        self._load_params_with_priority()

        # 自动生成路径配置
        self._generate_paths()

        # 检查必要参数是否已提供
        self._validate_required_params()

        # 初始化 日志配置
        self.logger_init()

    @classmethod
    def _load_params(cls) -> Dict[str, Any]:
        """
        加载参数定义文件 params.json。
        :return: 参数定义字典
        """
        params_file = ROOT_PATH / "params.json"
        try:
            with params_file.open("r", encoding="utf-8") as file:
                return json.load(file)
        except FileNotFoundError:
            logger.warning(f"参数定义文件 {params_file} 未找到。")
            return {}

    def _load_from_file(self):
        """
        从 .env 文件加载环境变量到 os.environ。
        """
        env_file = Path(self.env_path) / ".lol.env"
        if env_file.exists():
            load_dotenv(dotenv_path=env_file, override=True)
            logger.debug(f"环境变量文件加载成功: {env_file}")
        else:
            logger.warning(f"环境变量文件未找到: {env_file}")

    def _load_from_kwargs(self, kwargs: Dict[str, Any]):
        """
        处理传入的 kwargs 参数，并同步更新到环境变量。
        """
        for key, value in kwargs.items():
            if key not in {"env_path", "env_prefix"}:  # 忽略特殊参数
                # 设置参数值并标记来源
                self._set(key, value, source="init_args")
                # 同步写入到环境变量
                os.environ[f"{self.env_prefix}{key.upper()}"] = str(value)

    def _load_params_with_priority(self):
        """
        统一加载参数：从环境变量和默认值加载参数。
        优先级：环境变量 > 默认值
        """
        for param, metadata in self.params.items():
            if param not in self.settings:  # 如果参数尚未设置，才进行加载
                # 尝试从环境变量加载
                value = os.getenv(f"{self.env_prefix}{param.upper()}", None)
                if value is not None:
                    self._set(param, value, source="environment")
                else:
                    # 如果环境变量未设置，加载默认值
                    default_value = metadata.get("default", None)
                    if default_value is not None:
                        self._set(param, default_value, source="default")

    def _set(self, key: str, value: Any, source: str):
        """
        设置参数值，统一记录来源和类型转换。
        """
        key = key.upper()
        if key in self.params:
            metadata = self.params[key]
            _type = metadata.get("type", "str")
            type_func = {
                "str": str,
                "path": lambda x: Path(x) if x else None,
                "list": lambda x: x.split(",") if isinstance(x, str) else x,
            }
            self.settings[key] = type_func[_type](value)
            self.debug_source[key] = source
        else:
            self.settings[key] = value  # 对于手动设置的值，直接保存
            self.debug_source[key] = source

    def _generate_paths(self):
        """
        自动生成相关路径配置。
        """
        if "OUTPUT_PATH" in self.settings and "GAME_PATH" in self.settings:
            out_path = Path(self.settings["OUTPUT_PATH"])
            game_path = Path(self.settings["GAME_PATH"])

            # 音频目录, 最终解包生成的音频文件都放在这
            self.set_manual("AUDIO_PATH", out_path / "audios")

            # 缓存目录, 解包生成的一些文件会放在这里, 可以删除
            self.set_manual("TEMP_PATH", out_path / "temps")

            # 日志目录, 一些文件解析错误不会关闭程序而是记录在日志中
            self.set_manual("LOG_PATH", out_path / "logs")

            # 哈希目录, 存放所有与 k,v 相关数据
            self.set_manual("HASH_PATH", out_path / "hashes")

            # 有关于游戏内的数据文件
            self.set_manual("MANIFEST_PATH", out_path / "manifest")

            # 游戏版本文件, 用来记录当前解包文件的版本
            self.set_manual("LOCAL_VERSION_FILE", out_path / "game_version")

            # 游戏英雄文件目录 (Game/DATA/FINAL/Champions)
            self.set_manual("GAME_CHAMPION_PATH", game_path / "Game" / "DATA" / "FINAL" / "Champions")

            # 游戏地图(公共)文件目录 (Game/DATA/FINAL/Maps/Shipping)
            self.set_manual("GAME_MAPS_PATH", game_path / "Game" / "DATA" / "FINAL" / "Maps" / "Shipping")

            # 游戏大厅资源目录
            self.set_manual("GAME_LCU_PATH", game_path / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data")

            # 修正区域配置
            if self.settings.get("GAME_REGION", "").lower() == "en_us":
                self.settings["GAME_REGION"] = "default"

    def _validate_required_params(self):
        """
        检查所有必需参数是否已设置。
        """
        missing_params = []
        for param, metadata in self.params.items():
            if metadata.get("required", False) and param not in self.settings:
                missing_params.append(param)
        if missing_params:
            raise ValueError(f"缺少必要参数: {', '.join(missing_params)}")

    def logger_init(self):
        logger.configure(handlers=[{"sink": sys.stdout, "level": int(self.settings["DEBUG"]), "enqueue": True}])

    def debug_parameters(self):
        """
        输出所有参数及其来源，用于调试。
        """
        logger.debug("当前加载的参数及来源:")
        for key, value in self.settings.items():
            source = self.debug_source.get(key, "unknown")
            logger.debug(f"{key}: {value} (来源: {source})")

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取参数值。
        """
        return self.settings.get(key.upper(), default)

    def set_manual(self, key: str, value: Any):
        """
        手动设置参数值并记录来源。
        """
        self._set(key, value, source="manual")

    @classmethod
    def instance(cls, **kwargs):
        """
        获取单例实例，支持初始化参数。
        """
        return cls(**kwargs)
