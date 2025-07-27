# 🐍 If the implementation is hard to explain, it's a bad idea.
# 🐼 很难解释的，必然是坏方法
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2022/8/26 14:00
# @Update  : 2025/7/28 7:44
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

# 当前工作目录（通常是项目的根目录）
WORK_DIR = Path(os.getcwd())


class Config(metaclass=Singleton):
    """配置管理类，使用Singleton元类确保线程安全的单例模式"""

    # 内置参数定义
    DEFAULT_PARAMS = {
        "GAME_PATH": {"type": "path", "required": True, "help": "游戏根目录", "short": "g"},
        "GAME_REGION": {"type": "str", "default": "zh_CN", "help": "游戏区域", "short": "r"},
        "OUTPUT_PATH": {"type": "path", "required": True, "help": "输出目录", "short": "o"},
        "EXCLUDE_TYPE": {
            "type": "list",
            "default": "SFX,MUSIC",
            "help": "排除的音频类型 (逗号分隔), 例如 'SFX,MUSIC'。可用类型: VO, SFX, MUSIC",
            "short": "t",
        },
        "GROUP_BY_TYPE": {
            "type": "bool",
            "default": False,
            "help": """是否按音频类型对输出目录进行分组. 
# False (默认): audios/Champions/英雄/皮肤/类型/...
# True: audios/类型/Champions/英雄/皮肤/...""",
            "short": "b",
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
    }

    def __init__(
        self,
        env_path: StrPath | None = None,
        env_prefix: str = "LOL_",
        force_reload: bool = False,
        dev_mode: bool = False,
    ):
        """
        初始化配置管理

        :param env_path: 环境变量文件路径（.env文件）
        :param env_prefix: 环境变量前缀
        :param force_reload: 是否强制重新加载配置，即使是单例的重复初始化
        :param dev_mode: 是否使用开发环境配置
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
        self.dev_mode = dev_mode  # 是否处于开发环境
        self.using_work_dir = False  # 是否使用工作目录作为默认路径

        logger.debug(
            f"初始化Config实例: env_path={env_path}, env_prefix={env_prefix}, "
            f"force_reload={force_reload}, dev_mode={dev_mode}"
        )

        # 如果未指定env_path，则使用当前工作目录
        if env_path is None:
            env_path = WORK_DIR
            self.using_work_dir = True
            logger.debug(f"未指定env_path，使用当前工作目录: {env_path}")

        # 加载环境变量文件
        self._load_env_file(env_path, dev_mode)

        # 加载所有配置
        self._load_configs()

        # 生成派生路径
        self._generate_paths()

        # 验证必须的参数
        self._validate_required()

    def __str__(self):
        """提供配置实例的字符串表示，用于调试和测试"""
        info = [
            f"Config(env_prefix={self.env_prefix}",
            f"dev_mode={self.dev_mode}",
            f"settings_count={len(self.settings)}",
        ]

        if self.using_work_dir:
            info.append("Using working directory as default")

        return ", ".join(info) + ")"

    def reload(self, env_path: StrPath | None = None, env_prefix: str | None = None, dev_mode: bool | None = None):
        """
        重新加载配置（从环境变量或默认值）

        :param env_path: 环境变量文件路径（.env文件）
        :param env_prefix: 环境变量前缀
        :param dev_mode: 是否使用开发环境配置
        :return: None
        """
        logger.debug(f"重新加载配置: env_path={env_path}, env_prefix={env_prefix}, dev_mode={dev_mode}")

        # 如果提供了新的环境变量前缀，则更新
        if env_prefix is not None:
            self.env_prefix = env_prefix

        # 如果提供了新的开发模式设置，则更新
        if dev_mode is not None:
            self.dev_mode = dev_mode

        # 清空当前设置和来源记录
        prev_count = len(self.settings)
        self.settings.clear()
        self.sources.clear()
        logger.debug(f"已清除 {prev_count} 项配置设置")

        # 如果未指定env_path，则使用当前工作目录
        if env_path is None:
            env_path = WORK_DIR
            self.using_work_dir = True
            logger.debug(f"未指定env_path，使用当前工作目录: {env_path}")
        else:
            self.using_work_dir = False

        # 加载环境变量文件
        self._load_env_file(env_path, self.dev_mode)

        # 重新加载所有配置
        self._load_configs()

        # 生成派生路径
        self._generate_paths()

        # 验证必须的参数
        self._validate_required()

        logger.debug(f"配置重新加载完成，共 {len(self.settings)} 项")

    def _load_env_file(self, env_path: StrPath, dev_mode: bool = False):
        """
        加载环境变量文件

        :param env_path: 环境变量文件路径
        :param dev_mode: 是否使用开发环境配置
        :return: None
        """
        # 常规环境变量文件
        env_file = Path(env_path) / ".lol.env"

        # 开发环境变量文件
        dev_env_file = Path(env_path) / ".lol.env.dev"

        # 根据模式选择使用的文件
        target_file = dev_env_file if dev_mode and dev_env_file.exists() else env_file

        try:
            if target_file.exists():
                load_dotenv(dotenv_path=target_file, override=True)
                logger.debug(f"已加载环境变量文件: {target_file}" + (" (开发环境)" if dev_mode else ""))
                return

            # 如果请求开发环境但文件不存在，则提示并回退到常规环境文件
            if dev_mode and not dev_env_file.exists() and env_file.exists():
                logger.warning(f"开发环境文件 {dev_env_file} 不存在，使用常规环境文件 {env_file}")
                load_dotenv(dotenv_path=env_file, override=True)
                logger.debug(f"已加载环境变量文件: {env_file}")
            elif env_file.exists():
                load_dotenv(dotenv_path=env_file, override=True)
                logger.debug(f"已加载环境变量文件: {env_file}")
            else:
                logger.warning(f"环境变量文件不存在: {target_file}")
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

        # 输出所有配置项的详细信息
        # 使用日志级别DEBUG或更低时详细输出
        logger.debug("当前所有配置项:")
        for key, value in sorted(self.settings.items()):
            source = self.sources.get(key, "unknown")
            logger.debug(f"  - {key} = {value} (来源: {source})")

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
        生成派生路径配置，并创建相应目录

        :return: None
        """
        if "OUTPUT_PATH" not in self.settings or "GAME_PATH" not in self.settings:
            return

        logger.debug(
            f"生成派生路径: OUTPUT_PATH={self.settings['OUTPUT_PATH']}, GAME_PATH={self.settings['GAME_PATH']}"
        )
        out_path = Path(self.settings["OUTPUT_PATH"])
        game_path = Path(self.settings["GAME_PATH"])

        # 设置派生路径
        paths_to_create = []

        # 音频目录, 最终解包生成的音频文件都放在这
        audio_path = out_path / "audios"
        self.set("AUDIO_PATH", audio_path, source="derived")
        paths_to_create.append(audio_path)

        # 缓存目录, 解包生成的一些文件会放在这里, 可以删除
        temp_path = out_path / "temps"
        self.set("TEMP_PATH", temp_path, source="derived")
        paths_to_create.append(temp_path)

        # 日志目录, 一些文件解析错误不会关闭程序而是记录在日志中
        log_path = out_path / "logs"
        self.set("LOG_PATH", log_path, source="derived")
        paths_to_create.append(log_path)

        # 哈希目录, 存放所有与 k,v 相关数据
        hash_path = out_path / "hashes"
        self.set("HASH_PATH", hash_path, source="derived")
        paths_to_create.append(hash_path)

        # 有关于游戏内的数据文件
        manifest_path = out_path / "manifest"
        self.set("MANIFEST_PATH", manifest_path, source="derived")
        paths_to_create.append(manifest_path)

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

        # 创建必要的目录
        for path in paths_to_create:
            try:
                if not path.exists():
                    logger.debug(f"创建目录: {path}")
                    path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.warning(f"创建目录失败: {path} - {str(e)}")

        # 输出所有派生路径的详细信息
        logger.debug("派生路径配置完成，当前所有路径相关配置:")
        for key, value in sorted(self.settings.items()):
            if isinstance(value, Path) or (isinstance(value, str) and ("PATH" in key or "DIR" in key)):
                source = self.sources.get(key, "unknown")
                logger.debug(f"  - {key} = {value} (来源: {source})")

    def __getattr__(self, name):
        """
        允许通过属性访问配置值
        例如: config.GAME_PATH 等同于 config.get("GAME_PATH")

        :param name: 配置键
        :return: 配置值
        :raises AttributeError: 如果配置键不存在
        """
        # 如果是大写的配置键，尝试从配置中获取
        if name.isupper() and name in self.settings:
            return self.settings[name]

        # 对于其他属性，引发AttributeError
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

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

    def is_dev_mode(self) -> bool:
        """
        检查是否处于开发模式

        :return: 是否处于开发模式
        """
        return self.dev_mode


class ConfigProxy:
    """
    Config类的代理，实现延迟初始化

    允许在需要时才真正初始化Config实例，用于处理CLI或GUI程序中
    配置文件可能在程序启动后才指定的情况。
    """

    def __init__(self):
        """
        初始化代理

        :return: None
        """
        self._real_config = None
        self._default_env_path = None
        self._default_env_prefix = "LOL_"
        self._default_dev_mode = False

    def set_default_params(self, env_path=None, env_prefix="LOL_", dev_mode=False):
        """
        设置默认初始化参数，但不立即初始化Config

        :param env_path: 环境变量文件路径
        :param env_prefix: 环境变量前缀
        :param dev_mode: 是否使用开发环境配置
        :return: self (用于链式调用)
        """
        self._default_env_path = env_path
        self._default_env_prefix = env_prefix
        self._default_dev_mode = dev_mode
        logger.debug(f"ConfigProxy: 设置默认参数 env_path={env_path}, env_prefix={env_prefix}, dev_mode={dev_mode}")
        return self

    def __getattr__(self, name):
        """
        拦截属性访问，确保实例存在

        :param name: 属性名称
        :return: 属性值
        """
        # 如果尚未创建实例，则使用默认或预设的参数创建
        if self._real_config is None:
            logger.debug(
                f"ConfigProxy: 首次访问时自动创建Config实例，使用预设参数 env_path={self._default_env_path}, dev_mode={self._default_dev_mode}"
            )
            self._real_config = Config(
                env_path=self._default_env_path, env_prefix=self._default_env_prefix, dev_mode=self._default_dev_mode
            )

        # 转发属性访问到实际的Config实例
        return getattr(self._real_config, name)

    def initialize(self, env_path=None, env_prefix=None, force_reload=False, dev_mode=None):
        """
        显式初始化配置

        :param env_path: 环境变量文件路径
        :param env_prefix: 环境变量前缀
        :param force_reload: 是否强制重新加载配置
        :param dev_mode: 是否使用开发环境配置
        :return: 配置实例
        """
        # 如果未指定参数，则使用预设参数
        if env_path is None:
            env_path = self._default_env_path
        if env_prefix is None:
            env_prefix = self._default_env_prefix
        if dev_mode is None:
            dev_mode = self._default_dev_mode

        logger.debug(f"ConfigProxy: 显式初始化 env_path={env_path}, env_prefix={env_prefix}, dev_mode={dev_mode}")

        if self._real_config is None:
            # 首次初始化
            self._real_config = Config(env_path=env_path, env_prefix=env_prefix, dev_mode=dev_mode)
        elif force_reload:
            # 强制重新加载
            self._real_config.reload(env_path=env_path, env_prefix=env_prefix, dev_mode=dev_mode)

        return self._real_config

    def is_initialized(self):
        """
        检查是否已经初始化

        :return: 是否已初始化
        """
        return self._real_config is not None


# 创建全局配置代理实例
config = ConfigProxy()

# 在模块级别导出
__all__ = ["Config", "config", "ConfigProxy"]
