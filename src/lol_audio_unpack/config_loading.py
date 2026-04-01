"""配置文件加载与持久化辅助模块。

该模块负责统一管理 ``lol_audio_unpack`` 的标准 INI 配置文件。
"""

from __future__ import annotations

import configparser
from pathlib import Path
from typing import Any

from loguru import logger

from lol_audio_unpack.config_schema import (
    COMMAND_CONFIG_FIELDS,
    SHARED_SETTING_FIELD_BY_INI_KEY,
    SHARED_SETTING_FIELDS,
    ConfigSection,
)
from lol_audio_unpack.utils.runtime_paths import RuntimePaths, detect_runtime_paths
from lol_audio_unpack.utils.type_hints import StrPath

DEFAULT_CONFIG_FILENAME = "lol-audio-unpack.ini"
DEFAULT_DEV_CONFIG_FILENAME = "lol-audio-unpack.dev.ini"
CONFIG_SECTION = ConfigSection.APP

_MISSING = object()



def resolve_default_config_file_path(
    *,
    dev_mode: bool = False,
    runtime_paths: RuntimePaths | None = None,
) -> Path:
    """返回默认 INI 配置文件路径。

    Args:
        dev_mode: 是否使用开发模式配置文件名。
        runtime_paths: 可选运行时路径快照，未提供时实时探测。

    Returns:
        默认配置文件的绝对路径。
    """
    runtime = runtime_paths or detect_runtime_paths()
    filename = DEFAULT_DEV_CONFIG_FILENAME if dev_mode else DEFAULT_CONFIG_FILENAME
    return runtime.config_root / filename


def _load_config_parser(
    config_file: StrPath,
    *,
    require_exists: bool,
) -> configparser.ConfigParser | None:
    """读取 INI 配置文件并返回 parser。"""
    config_path = Path(config_file)
    if not config_path.exists():
        if require_exists:
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        return None

    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(config_path, encoding="utf-8")
    return parser


def load_settings_from_config_file(
    config_file: StrPath,
    *,
    require_exists: bool = True,
) -> dict[str, str]:
    """从标准 INI 配置文件读取共享设置。

    Args:
        config_file: INI 配置文件路径。
        require_exists: 为 ``True`` 时，文件不存在直接抛错。

    Returns:
        读取到的共享设置，键名统一为 ``AppContext`` 使用的内部大写键。

    Raises:
        FileNotFoundError: 需要文件存在但实际不存在时抛出。
    """
    parser = _load_config_parser(config_file, require_exists=require_exists)
    if parser is None:
        return {}
    if not parser.has_section(ConfigSection.APP):
        return {}

    settings: dict[str, str] = {}
    for raw_key, raw_value in parser.items(ConfigSection.APP):
        field = SHARED_SETTING_FIELD_BY_INI_KEY.get(raw_key.strip().lower())
        if field is None:
            logger.warning(f"忽略未知配置项: {raw_key}")
            continue
        settings[field.key] = raw_value.strip()
    return settings


def write_settings_to_config_file(
    config_file: StrPath,
    settings: dict[str, Any],
) -> None:
    """将共享设置写回标准 INI 配置文件。

    Args:
        config_file: INI 配置文件路径。
        settings: 待写入的共享设置，键名使用内部大写格式。
    """
    config_path = Path(config_file)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser[ConfigSection.APP] = {}
    section = parser[ConfigSection.APP]

    for field in SHARED_SETTING_FIELDS:
        if field.key not in settings:
            continue
        value = settings[field.key]
        if value is None:
            continue
        section[field.ini_key] = str(value).lower() if isinstance(value, bool) else str(value)

    with config_path.open("w", encoding="utf-8") as handle:
        parser.write(handle)


def _parse_command_value(
    section: configparser.SectionProxy,
    *,
    ini_key: str,
    value_kind: str,
) -> Any:
    """按字段定义解析命令配置值。"""
    if ini_key not in section:
        return _MISSING
    if value_kind == "bool":
        return section.getboolean(ini_key)
    if value_kind == "int":
        return section.getint(ini_key)

    value = section.get(ini_key, fallback="").strip()
    return None if not value else value


def load_command_config_from_file(
    config_file: StrPath,
    *,
    command: str,
    require_exists: bool = True,
) -> dict[str, Any]:
    """从标准 INI 读取指定子命令的运行参数。"""
    parser = _load_config_parser(config_file, require_exists=require_exists)
    if parser is None or command not in COMMAND_CONFIG_FIELDS or not parser.has_section(command):
        return {}

    section = parser[command]
    values: dict[str, Any] = {}
    for field in COMMAND_CONFIG_FIELDS[command]:
        value = _parse_command_value(section, ini_key=field.ini_key, value_kind=field.value_kind)
        if value is _MISSING:
            continue
        values[field.attr] = value
    return values
