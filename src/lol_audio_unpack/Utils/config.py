# 🐍 If the implementation is hard to explain, it's a bad idea.
# 🐼 很难解释的，必然是坏方法
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2022/8/26 14:00
# @Update  : 2025/7/23 6:40
# @Detail  : config.py


"""
配置管理模块 - 提供全局配置访问

使用方法:
    from lol_audio_unpack.Utils.config import config

    # 获取配置
    game_path = config.get("GAME_PATH")

    # 设置配置
    config.set("DEBUG", 10)
"""

import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from loguru import logger

from lol_audio_unpack.Utils.common import Singleton
from lol_audio_unpack.Utils.type_hints import StrPath

ROOT_PATH = Path(__file__).resolve().parent.parent


class Config(metaclass=Singleton):
    """配置管理类，使用Singleton元类确保线程安全的单例模式"""

    # 内置参数定义
    DEFAULT_PARAMS = {
        "GAME_PATH": {"type": "path", "required": True, "help": "游戏根目录", "short": "g"},
        "GAME_REGION": {"type": "str", "default": "zh_CN", "help": "游戏区域", "short": "r"},
        "OUTPUT_PATH": {"type": "path", "required": True, "help": "输出目录", "short": "o"},
        "INCLUDE_TYPE": {
            "type": "list",
            "default": "VO, SFX, MUSIC",
            "help": "排除的类型，例如 VO, SFX, MUSIC",
            "short": "t",
        },
        "INCLUDE_NAME": {"type": "list", "help": "名称过滤条件，例如 map11, Aatrox", "short": "n"},
        "INCLUDE_CATEGORY": {"type": "list", "help": "分类过滤条件，例如 maps, characters", "short": "c"},
        "VGMSTREAM_PATH": {"type": "path", "help": "VGMSTREAM 路径", "short": "v"},
        "AUDIO_FORMATE": {
            "type": "str",
            "default": "wem",
            "help": "输出音频格式，VGMSTREAM支持的转码格式，常见的wav、mp3、ogg等均支持",
            "short": "f",
        },
        "DEBUG": {
            "type": "str",
            "default": "5",
            "help": "调试等级，TRACE 5, DEBUG 10, INFO 20, SUCCESS 25, WARNING 30, ERROR 40, CRITICAL 50",
            "short": "d",
        },
    }

    def __init__(self, env_path: StrPath | None = None, env_prefix: str = "LOL_", force_reload: bool = False):
        """
        初始化配置管理

        :param env_path: 环境变量文件路径（.env文件）
        :param env_prefix: 环境变量前缀
        :param force_reload: 是否强制重新加载配置，即使是单例的重复初始化
        :return: None
        """
        # 检查是否已经初始化（单例模式下，__init__可能会被多次调用）
        if hasattr(self, "initialized") and not force_reload:
            logger.debug("Config已初始化且未强制重新加载，跳过初始化")
            return

        # 初始化基础配置
        self.initialized = True
        self.env_prefix = env_prefix
        self.params = self.DEFAULT_PARAMS  # 使用内置参数定义
        self.settings: dict[str, Any] = {}  # 保存配置值
        self.sources: dict[str, str] = {}  # 记录配置来源

        logger.debug(f"初始化Config实例: env_path={env_path}, env_prefix={env_prefix}, force_reload={force_reload}")

        # 加载环境变量文件
        if env_path:
            self._load_env_file(env_path)

        # 加载所有配置
        self._load_configs()

        # 生成派生路径
        self._generate_paths()

        # 验证必须的参数
        self._validate_required()

        # 初始化日志
        self._setup_logging()

    def reload(self, env_path: StrPath | None = None, env_prefix: str | None = None):
        """
        重新加载配置（从环境变量或默认值）

        :param env_path: 环境变量文件路径（.env文件）
        :param env_prefix: 环境变量前缀
        :return: None
        """
        logger.debug(f"重新加载配置: env_path={env_path}, env_prefix={env_prefix}")

        # 如果提供了新的环境变量前缀，则更新
        if env_prefix is not None:
            self.env_prefix = env_prefix

        # 清空当前设置和来源记录
        prev_count = len(self.settings)
        self.settings.clear()
        self.sources.clear()
        logger.debug(f"已清除 {prev_count} 项配置设置")

        # 加载环境变量文件
        if env_path:
            self._load_env_file(env_path)

        # 重新加载所有配置
        self._load_configs()

        # 生成派生路径
        self._generate_paths()

        # 验证必须的参数
        self._validate_required()

        # 重新初始化日志
        self._setup_logging()

        logger.debug(f"配置重新加载完成，共 {len(self.settings)} 项")

    def _load_env_file(self, env_path: StrPath):
        """
        加载环境变量文件

        :param env_path: 环境变量文件路径
        :return: None
        """
        env_file = Path(env_path) / ".lol.env"
        try:
            if env_file.exists():
                load_dotenv(dotenv_path=env_file, override=True)
                logger.debug(f"已加载环境变量文件: {env_file}")
        except Exception as e:
            logger.error(f"加载环境变量文件失败: {str(e)}")

    def _load_configs(self):
        """
        从各种来源加载配置

        :return: None
        """
        logger.debug("开始加载配置")

        # 获取所有环境变量前缀为env_prefix的环境变量
        prefix_len = len(self.env_prefix)
        for env_name, env_value in os.environ.items():
            if env_name.startswith(self.env_prefix):
                param_name = env_name[prefix_len:]
                logger.debug(f"从环境变量加载配置: {param_name}={env_value}")
                self._set_value(param_name, env_value, "env")

        # 从默认值加载未设置的配置
        for param_name, param_info in self.params.items():
            if param_name not in self.settings and "default" in param_info:
                default_value = param_info["default"]
                logger.debug(f"使用默认值: {param_name}={default_value}")
                self._set_value(param_name, default_value, "default")
            elif param_name not in self.settings:
                logger.debug(f"配置项无环境变量且无默认值: {param_name}")

        logger.debug(f"配置加载完成，共 {len(self.settings)} 项")

    def _set_value(self, key: str, value: Any, source: str):
        """
        设置配置值并进行类型转换

        :param key: 配置键
        :param value: 配置值
        :param source: 配置来源
        :return: None
        """
        if key in self.params:
            # 获取类型信息
            param_type = self.params[key].get("type", "str")

            # 类型转换
            try:
                if param_type == "path":
                    value = Path(value) if value else None
                elif param_type == "list":
                    if isinstance(value, str):
                        value = [item.strip() for item in value.split(",")]
                    elif not isinstance(value, list):
                        value = list(value) if value else []
                elif param_type == "int":
                    value = int(value)
                elif param_type == "float":
                    value = float(value)
                elif param_type == "bool":
                    if isinstance(value, str):
                        value = value.lower() in ("true", "yes", "1", "t", "y")
                    else:
                        value = bool(value)
            except (ValueError, TypeError) as e:
                logger.warning(f"类型转换失败 {key}={value} (类型:{param_type}): {str(e)}")

        # 保存值和来源
        self.settings[key] = value
        self.sources[key] = source

    def _generate_paths(self):
        """
        生成派生路径配置

        :return: None
        """
        if "OUTPUT_PATH" not in self.settings or "GAME_PATH" not in self.settings:
            return

        out_path = Path(self.settings["OUTPUT_PATH"])
        game_path = Path(self.settings["GAME_PATH"])

        # 设置派生路径
        # 音频目录, 最终解包生成的音频文件都放在这
        self.set("AUDIO_PATH", out_path / "audios", source="derived")

        # 缓存目录, 解包生成的一些文件会放在这里, 可以删除
        self.set("TEMP_PATH", out_path / "temps", source="derived")

        # 日志目录, 一些文件解析错误不会关闭程序而是记录在日志中
        self.set("LOG_PATH", out_path / "logs", source="derived")

        # 哈希目录, 存放所有与 k,v 相关数据
        self.set("HASH_PATH", out_path / "hashes", source="derived")

        # 有关于游戏内的数据文件
        self.set("MANIFEST_PATH", out_path / "manifest", source="derived")

        # 游戏版本文件, 用来记录当前解包文件的版本
        self.set("LOCAL_VERSION_FILE", out_path / "game_version", source="derived")

        # 游戏相关路径
        # 游戏英雄文件目录 (Game/DATA/FINAL/Champions)
        self.set("GAME_CHAMPION_PATH", game_path / "Game" / "DATA" / "FINAL" / "Champions", source="derived")

        # 游戏地图(公共)文件目录 (Game/DATA/FINAL/Maps/Shipping)
        self.set("GAME_MAPS_PATH", game_path / "Game" / "DATA" / "FINAL" / "Maps" / "Shipping", source="derived")

        # 游戏大厅资源目录
        self.set("GAME_LCU_PATH", game_path / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data", source="derived")

        # 修正区域配置
        if self.get("GAME_REGION", "").lower() == "en_us":
            self.set("GAME_REGION", "default", source="derived")

    def _validate_required(self):
        """
        验证必须的参数

        :return: None
        """
        missing = []
        for name, info in self.params.items():
            if info.get("required", False) and (name not in self.settings or not self.settings[name]):
                missing.append(name)

        if missing:
            logger.error(f"缺少必要的配置项: {', '.join(missing)}")
            # 对于严重的配置缺失，可以考虑抛出异常
            # raise ValueError(f"缺少必要的配置项: {', '.join(missing)}")

    def _setup_logging(self):
        """
        设置日志记录器

        :return: None
        """
        try:
            debug_level = int(self.get("DEBUG", 20))
            logger.configure(handlers=[{"sink": sys.stdout, "level": debug_level, "enqueue": True}])

            log_path = self.get("LOG_PATH")
            if log_path:
                Path(log_path).mkdir(parents=True, exist_ok=True)
                logger.add(
                    Path(log_path) / "{time:YYYY-MM-DD}.log", rotation="00:00", retention="7 days", level="DEBUG"
                )
        except Exception as e:
            print(f"日志初始化失败: {str(e)}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值

        :param key: 配置键
        :param default: 默认值（如果配置不存在）
        :return: 配置值或默认值
        """
        return self.settings.get(key, default)

    def set(self, key: str, value: Any, source: str = "manual"):
        """
        设置配置值

        :param key: 配置键
        :param value: 配置值
        :param source: 配置来源（用于跟踪）
        :return: None
        """
        self._set_value(key, value, source)

        # 同步到环境变量（可选）
        # os.environ[f"{self.env_prefix}{key}"] = str(value)

    def dump(self):
        """
        打印所有配置及其来源

        :return: None
        """
        for key, value in sorted(self.settings.items()):
            source = self.sources.get(key, "unknown")
            logger.info(f"{key}: {value} (来源: {source})")

    def as_dict(self) -> dict[str, Any]:
        """
        返回所有配置为字典

        :return: 包含所有配置的字典
        """
        return dict(self.settings)

    @staticmethod
    def reset_instance():
        """
        重置Config的单例实例，主要用于测试场景

        :return: None
        """
        if Config in Singleton._instances:
            logger.debug("重置Config单例实例")
            del Singleton._instances[Config]
            logger.debug("Config单例实例已重置")
        else:
            logger.debug("Config单例实例不存在，无需重置")


# 创建全局配置实例
config = Config()

# 在模块级别导出
__all__ = ["Config", "config"]
