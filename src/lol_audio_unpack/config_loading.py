"""配置文件加载与持久化辅助模块。

该模块负责统一管理 ``lol_audio_unpack`` 的标准 INI 配置文件。
"""

from __future__ import annotations

import configparser
from pathlib import Path
from typing import Any

from loguru import logger

from lol_audio_unpack.utils.runtime_paths import RuntimePaths, detect_runtime_paths
from lol_audio_unpack.utils.type_hints import StrPath

CONFIG_SECTION = "app"
DEFAULT_CONFIG_FILENAME = "lol-audio-unpack.ini"
DEFAULT_DEV_CONFIG_FILENAME = "lol-audio-unpack.dev.ini"

SETTING_KEY_TO_CONFIG_KEY: dict[str, str] = {
    "SOURCE_MODE": "source_mode",
    "GAME_PATH": "game_path",
    "OUTPUT_PATH": "output_path",
    "GAME_REGION": "game_region",
    "EXCLUDE_TYPE": "exclude_type",
    "CLEANUP_REMOTE": "cleanup_remote",
    "GROUP_BY_TYPE": "group_by_type",
    "REMOTE_LIVE_REGION": "remote_live_region",
    "REMOTE_VERSION": "remote_version",
    "REMOTE_LCU_MANIFEST_URL": "remote_lcu_manifest_url",
    "REMOTE_GAME_MANIFEST_URL": "remote_game_manifest_url",
    "WWISER_PATH": "wwiser_path",
}
CONFIG_KEY_TO_SETTING_KEY: dict[str, str] = {
    config_key: setting_key for setting_key, config_key in SETTING_KEY_TO_CONFIG_KEY.items()
}
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
    config_path = Path(config_file)
    if not config_path.exists():
        if require_exists:
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        return {}

    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(config_path, encoding="utf-8")
    if not parser.has_section(CONFIG_SECTION):
        return {}

    settings: dict[str, str] = {}
    for raw_key, raw_value in parser.items(CONFIG_SECTION):
        setting_key = CONFIG_KEY_TO_SETTING_KEY.get(raw_key.strip().lower())
        if setting_key is None:
            logger.warning(f"忽略未知配置项: {raw_key}")
            continue
        settings[setting_key] = raw_value.strip()
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
    parser[CONFIG_SECTION] = {}
    section = parser[CONFIG_SECTION]

    for setting_key, config_key in SETTING_KEY_TO_CONFIG_KEY.items():
        if setting_key not in settings:
            continue
        value = settings[setting_key]
        if value is None:
            continue
        section[config_key] = str(value).lower() if isinstance(value, bool) else str(value)

    with config_path.open("w", encoding="utf-8") as handle:
        parser.write(handle)
